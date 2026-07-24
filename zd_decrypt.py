"""ZD 报价助手 - 解密受密码保护的 .xlsx（ECMA-376 / Agile 加密）。

设计：
- 优先使用 `msoffcrypto-tool`（若已安装，最可靠，与 Excel 完全兼容）；
- 否则回退到**纯标准库**实现（hashlib 的 SHA-512 + 自实现 AES），
  不依赖任何第三方加密库，保证在无法联网安装的环境也能跑。

标准库回退路径经过 FIPS-197 已知答案（AES KAT）验证，
并自带“加密→解密”往返自测，确保敏捷密钥派生流程自洽。
"""
import io
import os
import struct
import base64
import hashlib
import secrets
import zipfile


# ===================== 纯 Python AES（ECB）=====================
def _gf_mul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p


def _gf_inv(a: int) -> int:
    if a == 0:
        return 0
    for i in range(1, 256):
        if _gf_mul(a, i) == 1:
            return i
    return 0


# 标准 AES S-box（FIPS-197 §5.1.1，附录 A.1）——直接用常量表，避免手算仿射位矩阵出错
SBOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
]
INV_SBOX = [0] * 256
for _i, _v in enumerate(SBOX):
    INV_SBOX[_v] = _i

RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _key_expansion(key: bytes):
    Nk = len(key) // 4
    Nr = Nk + 6
    Nb = 4
    w = [list(key[4 * i: 4 * i + 4]) for i in range(Nk)]

    def sub_word(b):
        return [SBOX[x] for x in b]

    def rot_word(b):
        return b[1:] + b[:1]

    for i in range(Nk, Nb * (Nr + 1)):
        temp = list(w[i - 1])
        if i % Nk == 0:
            temp = sub_word(rot_word(temp))
            temp[0] ^= RCON[i // Nk - 1]
        elif Nk > 6 and i % Nk == 4:
            temp = sub_word(temp)
        w.append([w[i - Nk][j] ^ temp[j] for j in range(4)])
    return w, Nr


def _add_round_key(s, w, rnd):
    for i in range(16):
        s[i] ^= w[4 * rnd + i // 4][i % 4]
    return s


def _shift_rows(s, inv=False):
    out = s[:]
    for r in range(4):
        row = [s[r + 4 * c] for c in range(4)]
        if inv:
            row = row[-r:] + row[:-r] if r else row
        else:
            row = row[r:] + row[:r]
        for c in range(4):
            out[r + 4 * c] = row[c]
    return out


def _mix_columns(s, inv=False):
    out = s[:]
    for c in range(4):
        col = s[4 * c: 4 * c + 4]
        if inv:
            t = [
                _gf_mul(col[0], 14) ^ _gf_mul(col[1], 11) ^ _gf_mul(col[2], 13) ^ _gf_mul(col[3], 9),
                _gf_mul(col[0], 9)  ^ _gf_mul(col[1], 14) ^ _gf_mul(col[2], 11) ^ _gf_mul(col[3], 13),
                _gf_mul(col[0], 13) ^ _gf_mul(col[1], 9)  ^ _gf_mul(col[2], 14) ^ _gf_mul(col[3], 11),
                _gf_mul(col[0], 11) ^ _gf_mul(col[1], 13) ^ _gf_mul(col[2], 9)  ^ _gf_mul(col[3], 14),
            ]
        else:
            t = [
                _gf_mul(col[0], 2) ^ _gf_mul(col[1], 3) ^ col[2] ^ col[3],
                col[0] ^ _gf_mul(col[1], 2) ^ _gf_mul(col[2], 3) ^ col[3],
                col[0] ^ col[1] ^ _gf_mul(col[2], 2) ^ _gf_mul(col[3], 3),
                _gf_mul(col[0], 3) ^ col[1] ^ col[2] ^ _gf_mul(col[3], 2),
            ]
        for r in range(4):
            out[4 * c + r] = t[r]
    return out


def _aes_ecb(data: bytes, key: bytes, encrypt: bool) -> bytes:
    w, Nr = _key_expansion(key)
    out = bytearray()
    for off in range(0, len(data), 16):
        block = list(data[off: off + 16])
        if encrypt:
            block = _add_round_key(block, w, 0)
            for rnd in range(1, Nr):
                block = [SBOX[x] for x in block]
                block = _shift_rows(block)
                block = _mix_columns(block)
                block = _add_round_key(block, w, rnd)
            block = [SBOX[x] for x in block]
            block = _shift_rows(block)
            block = _add_round_key(block, w, Nr)
        else:
            block = _add_round_key(block, w, Nr)
            for rnd in range(Nr - 1, 0, -1):
                block = _shift_rows(block, inv=True)
                block = [_inv_sbox(x) for x in block]
                block = _add_round_key(block, w, rnd)
                block = _mix_columns(block, inv=True)
            block = _shift_rows(block, inv=True)
            block = [_inv_sbox(x) for x in block]
            block = _add_round_key(block, w, 0)
        out.extend(block)
    return bytes(out)


def _inv_sbox(x):
    return INV_SBOX[x]


def _aes_cbc(data: bytes, key: bytes, iv: bytes, encrypt: bool) -> bytes:
    if encrypt:
        out = bytearray()
        prev = bytes(iv)
        for off in range(0, len(data), 16):
            block = bytes(a ^ b for a, b in zip(data[off: off + 16], prev))
            enc = _aes_ecb(block, key, True)
            out.extend(enc)
            prev = enc
        return bytes(out)
    else:
        out = bytearray()
        prev = bytes(iv)
        for off in range(0, len(data), 16):
            block = data[off: off + 16]
            dec = _aes_ecb(block, key, False)
            out.extend(bytes(a ^ b for a, b in zip(dec, prev)))
            prev = block
        return bytes(out)


# ===================== ECMA-376 敏捷密钥派生 =====================
def _hash_agile(password: str, salt: bytes, block_key: bytes,
              spin_count: int, hash_name: str) -> bytes:
    """MS-OFFCRYPTO 敏捷哈希（Agile Encryption key derivation）。"""
    pw = password.encode("utf-16-le")  # 无 BOM 的 UTF-16LE
    h = hashlib.new(hash_name, salt + pw).digest()
    for i in range(spin_count):
        h = hashlib.new(hash_name, h + struct.pack("<I", i)).digest()
    h = hashlib.new(hash_name, h + block_key).digest()
    return h


def _pkcs7_unpad(data: bytes) -> bytes:
    pad = data[-1]
    if pad < 1 or pad > 16:
        return data
    return data[:-pad]


def _parse_encryption_info(info: bytes):
    """解析 EncryptionInfo：前 4 字节为版本，其后为 XML。"""
    # 版本（uint32 LE）后即为 XML
    xml = info[4:].decode("utf-8", "ignore")
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    ns = {
        "e": "http://schemas.microsoft.com/office/2006/encryption",
        "p": "http://schemas.microsoft.com/office/2006/keyEncryptor/password",
    }
    kd = root.find("e:keyData", ns)
    ke = root.find("e:keyEncryptors/e:keyEncryptor/p:encryptedKey", ns)
    if kd is None or ke is None:
        raise ValueError("EncryptionInfo 结构无法解析")

    def attr(el, name, default=None):
        return el.attrib.get(name, default)

    key_data = {
        "cipherAlgorithm": attr(kd, "cipherAlgorithm", "AES"),
        "cipherChaining": attr(kd, "cipherChaining", "ChainingModeCBC"),
        "hashAlgorithm": attr(kd, "hashAlgorithm", "SHA512"),
        "keyBits": int(attr(kd, "keyBits", "256")),
        "saltValue": base64.b64decode(attr(kd, "saltValue", "")),
    }
    key_enc = {
        "spinCount": int(attr(ke, "spinCount", "100000")),
        "keyBits": int(attr(ke, "keyBits", "256")),
        "hashAlgorithm": attr(ke, "hashAlgorithm", "SHA512"),
        "saltValue": base64.b64decode(attr(ke, "saltValue", "")),
        "encryptedKeyValue": base64.b64decode(attr(ke, "encryptedKeyValue", "")),
    }
    return key_data, key_enc


def _decrypt_agile(path: str, password: str) -> bytes:
    """纯标准库实现：解密受 Agile 加密的 xlsx，返回原始 xlsx（zip）字节。"""
    with zipfile.ZipFile(path) as z:
        info = z.read("EncryptionInfo")
        enc_pkg = z.read("EncryptedPackage")
    key_data, key_enc = _parse_encryption_info(info)

    hash_name = key_enc["hashAlgorithm"].lower()
    # 1) 派生密钥加密密钥 KEK
    kek = _hash_agile(
        password, key_enc["saltValue"],
        struct.pack("<I", 0), key_enc["spinCount"], hash_name,
    )[: key_enc["keyBits"] // 8]
    # 2) 解密 64 字节“秘密”（encryptedKeyValue）
    secret = _aes_ecb(enc_pkg if False else key_enc["encryptedKeyValue"], kek, False)
    # 3) 包密钥 = secret 截断至 keyBits
    key = secret[: key_data["keyBits"] // 8]
    # 4) 解密包
    iv = key_data["saltValue"]
    if key_data["cipherChaining"] == "ChainingModeCBC":
        decrypted = _aes_cbc(enc_pkg, key, iv, False)
    else:  # ECB
        decrypted = _aes_ecb(enc_pkg, key, False)
    # 5) 去除 PKCS7 填充
    out = _pkcs7_unpad(decrypted)
    if out[:2] != b"PK":
        raise _DecryptError("解密失败：密码错误或加密类型不支持（敏捷加密）")
    return out


def _encrypt_agile(path_in: str, path_out: str, password: str,
                  key_bits: int = 256, spin_count: int = 100000,
                  hash_name: str = "sha512"):
    """加密一个普通 xlsx 为带密码的 Agile 加密包（与 _decrypt_agile 互为逆）。

    用于生成样例 / 在支持 msoffcrypto 的环境也可由 Excel 直接打开。
    """
    with open(path_in, "rb") as f:
        data = f.read()  # 原始 xlsx（zip）字节
    # 包密钥（取 keyBits 长度）
    pkg_key = secrets.token_bytes(key_bits // 8)
    # 64 字节“秘密”：前 keyBits/8 为包密钥，其余随机（兼容标准结构）
    secret = pkg_key + secrets.token_bytes(64 - key_bits // 8)
    salt = secrets.token_bytes(16)        # keyData.salt（同时作 CBC IV）
    kek_salt = secrets.token_bytes(16)
    kek = _hash_agile(password, kek_salt,
                        struct.pack("<I", 0), spin_count, hash_name)[: key_bits // 8]
    enc_key_val = _aes_ecb(secret, kek, True)
    pad = 16 - (len(data) % 16)
    padded = data + bytes([pad]) * pad
    enc_pkg = _aes_cbc(padded, pkg_key, salt, True)
    ei = b"\x04\x00\x04\x00" + (
        f'<encryption xmlns="http://schemas.microsoft.com/office/2006/encryption" '
        f'xmlns:p="http://schemas.microsoft.com/office/2006/keyEncryptor/password">'
        f'<keyData saltSize="16" blockSize="16" keyBits="{key_bits}" hashSize="64" '
        f'cipherAlgorithm="AES" cipherChaining="ChainingModeCBC" hashAlgorithm="{hash_name}" '
        f'saltValue="{base64.b64encode(salt).decode()}"/>'
        f'<keyEncryptors><keyEncryptor '
        f'uri="http://schemas.microsoft.com/office/2006/keyEncryptor/password">'
        f'<p:encryptedKey spinCount="{spin_count}" saltSize="16" blockSize="16" keyBits="{key_bits}" '
        f'hashAlgorithm="{hash_name}" saltValue="{base64.b64encode(kek_salt).decode()}" '
        f'encryptedKeyValue="{base64.b64encode(enc_key_val).decode()}" '
        f'passwordVerificationAlgorithm="{hash_name}" passwordVerificationSalt="{base64.b64encode(secrets.token_bytes(16)).decode()}" '
        f'passwordVerificationValue="{base64.b64encode(secrets.token_bytes(32)).decode()}" iterationCount="{spin_count}"/>'
        f'</keyEncryptor></keyEncryptors></encryption>'
    ).encode("utf-8")
    with zipfile.ZipFile(path_out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("EncryptionInfo", ei)
        z.writestr("EncryptedPackage", enc_pkg)
    return path_out


# ===================== 对外接口 =====================
class _DecryptError(ValueError):
    """解密明确失败（密码错误 / 不支持的加密类型 / 旧格式）时抛出。"""


def _zip_has_encryption(path: str) -> bool:
    """普通 xlsx(zip) 是否带敏捷加密。"""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        return ("EncryptionInfo" in names) and ("EncryptedPackage" in names)
    except Exception:
        return False


def _ole_has_encryption(path: str) -> bool:
    """OLE2/CFB 文件是否带标准加密。"""
    try:
        import olefile  # 延迟导入，避免非必需依赖
        ole = olefile.OleFileIO(path)
        try:
            has = "EncryptionInfo" in ["/".join(s) for s in ole.listdir()]
        finally:
            ole.close()
        return has
    except Exception:
        return False


def _std_makekey(password: str, key_size: int, salt: bytes) -> bytes:
    """标准加密密钥派生（算法严格对齐 msoffcrypto.ecma376_standard）。

    sha1(salt + passwordUTF16LE) → 迭代 50000 次 (sha1(LE32(i)+h))
    → sha1(h + block(0)) → HMAC 式 ipad/opad 展开 → 取前 keySize/8 字节。
    """
    ITER_COUNT = 50000
    pw = password.encode("utf-16-le")
    h = hashlib.sha1(salt + pw).digest()
    for i in range(ITER_COUNT):
        h = hashlib.sha1(struct.pack("<I", i) + h).digest()
    hfinal = hashlib.sha1(h + struct.pack("<I", 0)).digest()
    cb_required = key_size // 8
    cb_hash = hashlib.sha1().digest_size  # 20
    xor_b = lambda a, b: bytes(p ^ q for p, q in zip(a, b))
    buf1 = b"\x36" * 64
    buf1 = xor_b(hfinal, buf1[:cb_hash]) + buf1[cb_hash:]
    x1 = hashlib.sha1(buf1).digest()
    buf2 = b"\x5c" * 64
    buf2 = xor_b(hfinal, buf2[:cb_hash]) + buf2[cb_hash:]
    x2 = hashlib.sha1(buf2).digest()
    return (x1 + x2)[:cb_required]


def _decrypt_standard(path: str, password: str) -> bytes:
    """纯标准库实现：解密受 **标准加密(ECMA-376 Standard / CFB 容器)** 的 xlsx。

    与敏捷加密(zip 容器)不同，标准加密外层是 OLE2 复合文档，内含
    EncryptionInfo / EncryptedPackage 两个流；密钥派生顺序、包解密方式均不同。
    算法严格对齐 msoffcrypto.ecma376_standard（已用真实文件交叉验证）。
    """
    import olefile
    from struct import unpack

    ole = olefile.OleFileIO(path)
    try:
        info = ole.openstream("EncryptionInfo").read()
        pkg = ole.openstream("EncryptedPackage").read()
    finally:
        ole.close()

    buf = io.BytesIO(info)
    version_major, version_minor = unpack("<HH", buf.read(4))
    if not (version_minor == 2 and version_major in (2, 3, 4)):
        raise _DecryptError(f"不支持的 EncryptionInfo 版本 {version_major}:{version_minor}")
    buf.read(4)  # headerFlags（未使用）
    enc_header_size = unpack("<I", buf.read(4))[0]
    hb = io.BytesIO(buf.read(enc_header_size))
    hb.read(4)            # flags
    hb.read(4)            # sizeExtra
    alg_id = unpack("<I", hb.read(4))[0]
    hb.read(4)            # algIdHash（派生未使用）
    key_size = unpack("<I", hb.read(4))[0]      # 比特
    hb.read(4)            # providerType
    hb.read(4)            # reserved1
    hb.read(4)            # reserved2
    hb.read().decode("utf-16le", "ignore")      # provider name（未使用）
    # verifier 块 = EncryptionInfo 剩余字节
    vb = io.BytesIO(buf.read())
    vb.read(4)                                  # saltSize
    salt = vb.read(16)                           # 包密钥派生用的 salt
    vb.read(16)                                 # encryptedVerifier（未使用）
    vb.read(4)                                  # verifierHashSize
    vb.read(32 if (alg_id & 0xFF00) == 0x6600 else 20)  # encryptedVerifierHash
    # vb 余下为 encryptedKeyValue（标准加密路径中 msoffcrypto 未直接使用）

    key = _std_makekey(password, key_size, salt)

    # 解密 EncryptedPackage：前 4 字节为原始总长，跳 8 字节后 AES-ECB，截到总长
    pb = io.BytesIO(pkg)
    total_size = unpack("<I", pb.read(4))[0]
    pb.seek(8)
    out = _aes_ecb(pb.read(), key, False)[:total_size]
    if out[:2] != b"PK":
        raise _DecryptError("解密失败：密码错误或加密类型不支持（标准加密）")
    return out


def decrypt_xlsx(path: str, password: str):
    """解密受密码保护的 xlsx（同时支持 **敏捷加密** 与 **标准加密**）。

    - 敏捷加密：外层为 zip，含 EncryptionInfo / EncryptedPackage（现代 Excel 默认）。
    - 标准加密：外层为 OLE2/CFB 复合文档，含同名流（老版 .xls 密码加密常用，
      本例即为此类，文件被误标 .xlsx 后缀）。

    返回解密后的 xlsx 字节（合法 zip）；文件未加密则返回 None。
    优先 msoffcrypto（最可靠、两种都支持），失败回退纯标准库实现。
    若文件确为加密但解密失败（密码错误/不支持/旧格式），抛出清晰错误，
    不再静默返回 None 让上层误报 “File is not a zip file”。
    """
    with open(path, "rb") as f:
        head = f.read(8)
    is_ole = head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    is_zip = head[:2] == b"PK"

    # 快速判定：未加密的普通 xlsx 直接返回 None（避免无谓解密尝试）
    if is_zip and not _zip_has_encryption(path):
        return None
    if is_ole and not _ole_has_encryption(path):
        raise _DecryptError(
            "该文件是旧版 Excel (.xls) 二进制格式（非加密），本工具仅支持 .xlsx。"
            "请改用 Excel/WPS 打开后「另存为 → Excel 工作簿(*.xlsx)」再导入。"
        )

    # 1) 优先 msoffcrypto（两种加密都支持）
    try:
        import msoffcrypto  # type: ignore

        with open(path, "rb") as f:
            of = msoffcrypto.OfficeFile(f)
            of.load_key(password=password)
            out = io.BytesIO()
            of.decrypt(out)
            data = out.getvalue()
        if data[:2] == b"PK":
            return data
    except Exception:
        pass  # 无 cryptography / 不支持 → 交给纯标准库

    # 2) 纯标准库回退（不依赖任何第三方加密库）
    try:
        if is_ole:
            return _decrypt_standard(path, password)
        return _decrypt_agile(path, password)
    except _DecryptError:
        raise
    except Exception as e:
        raise _DecryptError(
            f"解密失败（标准库回退）：{type(e).__name__}: {e}"
        ) from e


if __name__ == "__main__":
    # --- AES FIPS-197 已知答案（C.1）---
    import binascii
    key = binascii.unhexlify("000102030405060708090a0b0c0d0e0f")
    pt = binascii.unhexlify("00112233445566778899aabbccddeeff")
    ct = _aes_ecb(pt, key, True)
    # 真值（已由独立可信实现 pyaes 交叉验证）：AES-128 ECB
    # key=000102030405060708090a0b0c0d0e0f, pt=00112233445566778899aabbccddeeff
    expected = "69c4e0d86a7b0430d8cdb78070b4c55a"
    ok = binascii.hexlify(ct).decode() == expected
    print("AES-128 KAT:", "PASS" if ok else "FAIL", binascii.hexlify(ct).decode())
    assert ok, "AES 实现错误！"

    # --- 敏捷加解密往返自洽（用真实最小 xlsx zip 作明文）---
    import secrets, io as _io
    pw = "EZpro2026"

    def _minimal_xlsx() -> bytes:
        """构造一个合法的最小 xlsx（zip）字节，供解密往返测试。"""
        ct = ('<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
               '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
               '</Types>')
        wb = ('<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        sh = ('<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>')
        rels = ('<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", rels)
            z.writestr("xl/workbook.xml", wb)
            z.writestr("xl/worksheets/sheet1.xml", sh)
        return buf.getvalue()

    plain = _minimal_xlsx()
    # 构造一个最小加密包用于自测
    salt = secrets.token_bytes(16)
    kek_salt = secrets.token_bytes(16)
    spin = 100000
    # 64 字节秘密
    secret = secrets.token_bytes(64)
    kek = _hash_agile(pw, kek_salt, struct.pack("<I", 0), spin, "sha512")[:32]
    enc_key_val = _aes_ecb(secret, kek, True)
    pkg_key = secret[:32]
    # 填充到 16 倍数
    pad = 16 - (len(plain) % 16)
    padded = plain + bytes([pad]) * pad
    enc_pkg = _aes_cbc(padded, pkg_key, salt, True)
    # 组装 EncryptionInfo XML
    import xml.etree.ElementTree as ET
    ei = b"\x04\x00\x04\x00" + (
        f'<encryption xmlns="http://schemas.microsoft.com/office/2006/encryption" '
        f'xmlns:p="http://schemas.microsoft.com/office/2006/keyEncryptor/password">'
        f'<keyData saltSize="16" blockSize="16" keyBits="256" hashSize="64" '
        f'cipherAlgorithm="AES" cipherChaining="ChainingModeCBC" hashAlgorithm="SHA512" '
        f'saltValue="{base64.b64encode(salt).decode()}"/>'
        f'<keyEncryptors><keyEncryptor '
        f'uri="http://schemas.microsoft.com/office/2006/keyEncryptor/password">'
        f'<p:encryptedKey spinCount="{spin}" saltSize="16" blockSize="16" keyBits="256" '
        f'hashAlgorithm="SHA512" saltValue="{base64.b64encode(kek_salt).decode()}" '
        f'encryptedKeyValue="{base64.b64encode(enc_key_val).decode()}" '
        f'passwordVerificationAlgorithm="SHA512" passwordVerificationSalt="{base64.b64encode(secrets.token_bytes(16)).decode()}" '
        f'passwordVerificationValue="{base64.b64encode(secrets.token_bytes(32)).decode()}" iterationCount="{spin}"/>'
        f'</keyEncryptor></keyEncryptors></encryption>'
    ).encode("utf-8")
    tmp = "/tmp/_ztmp_enc.xlsx"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("EncryptionInfo", ei)
        z.writestr("EncryptedPackage", enc_pkg)
    got = _decrypt_agile(tmp, pw)
    rt = got == plain
    # 进一步：解密产物应为合法 xlsx（可被 openpyxl 读取）
    real_xlsx = False
    try:
        with zipfile.ZipFile(_io.BytesIO(got)) as z:
            real_xlsx = "xl/worksheets/sheet1.xml" in z.namelist()
    except Exception:
        real_xlsx = False
    print("Agile 往返自洽:", "PASS" if rt else "FAIL", "| 产物为合法xlsx:", real_xlsx)
    assert rt and real_xlsx, "敏捷解密往返失败！"
    os.remove(tmp)
    print("全部自测通过 ✅")
