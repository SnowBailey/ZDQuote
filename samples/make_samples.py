"""生成样例数据：配单表 / 价格表 / 报价表（验证新价格体系 + 按物料编号关联）。

额外生成：
- 价格表_加密.xlsx：用默认密码 EZpro2026 加密的「价格表」（敏捷加密），验证导入带密码文件自动解密。
- 价格表_标准加密.xlsx：同样内容但用 **标准加密(ECMA-376 Standard / CFB 容器)**，
  模拟真实「带密码测试.xlsx」那类被误标 .xlsx 后缀的老版加密文件。
- 物料编码 1200000043 的特殊行：验证该编码强制价格覆盖
  （市场价=15000，其余统一=9000）。
"""
import os
import io
import struct
import tempfile
import openpyxl
import zd_config as C
import zd_decrypt as DEC


def _wb(path, sheets: dict):
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet()
        ws.title = name
        first = False
        for r in rows:
            ws.append(r)
    wb.save(path)
    print("  →", path)


def _encrypt_standard(plain: bytes, password: str, key_bits: int = 128) -> bytes:
    """反向实现「标准加密」，生成与真实 CFB 容器一致的文件（仅用于回归测试）。

    严格对齐 msoffcrypto.ecma376_standard 的解析/派生，确保
    zd_decrypt._decrypt_standard 能解回原始 zip。
    """
    import olefile  # 延迟导入（仅样例生成用）
    from msoffcrypto.method.container.ecma376_encrypted import ECMA376Encrypted

    salt = os.urandom(16)
    kek = DEC._std_makekey(password, key_bits, salt)  # 包密钥（msoffcrypto 简化流程）
    pad = 16 - (len(plain) % 16)
    padded = plain + b"\x00" * pad
    ct = DEC._aes_ecb(padded, kek, True)  # AES-ECB 加密
    enc_pkg = struct.pack("<I", len(plain)) + b"\x00" * 4 + ct  # 总长 + 4 零字节 + 密文

    csp = "Microsoft Enhanced RSA and AES Cryptographic Provider".encode("utf-16-le") + b"\x00\x00"
    header_blob = (
        struct.pack("<I", 0x24)        # flags
        + struct.pack("<I", 0)          # sizeExtra
        + struct.pack("<I", 0x660E)     # algId = AES-128
        + struct.pack("<I", 0x8004)     # algIdHash = SHA-1
        + struct.pack("<I", key_bits)     # keySize (bit)
        + struct.pack("<I", 0x18)        # providerType = PROV_RSA_AES
        + struct.pack("<I", 0)          # reserved1
        + struct.pack("<I", 0)          # reserved2
        + csp
    )
    enc_header_size = len(header_blob)
    verifier_blob = (
        struct.pack("<I", 16) + salt          # saltSize + salt(16)
        + b"\x00" * 16                          # encryptedVerifier（未用）
        + struct.pack("<I", 32) + b"\x00" * 32  # verifierHashSize + hash（未用）
    )
    info = (
        struct.pack("<HH", 4, 2)             # versionMajor=4, versionMinor=2 → 标准加密
        + struct.pack("<I", 0x24)            # headerFlags
        + struct.pack("<I", enc_header_size)
        + header_blob
        + verifier_blob
    )
    enc = ECMA376Encrypted(enc_pkg, info)
    buf = io.BytesIO()
    enc.write_to(buf)
    return buf.getvalue()


def make():
    # 配单表：2 个品牌页（含产品编码，用于与价格表关联）
    cfg = {
        "品牌A": [
            ["序号", "设备名称", "品牌", "型号", "规格", "国别", "数量", "单位", "备注", "产品编码", "标底参数"],
            [1, "防火墙", "华为", "FW-100", "1U", "中国", 2, "台", "核心网", "HA100", "参数A"],
            [2, "交换机", "华为", "SW-200", "24口", "中国", 5, "台", "", "HA200", "参数B"],
            [3, "特批设备", "小米", "SP-999", "1U", "中国", 1, "台", "特批", "1200000043", "参数SP"],
        ],
        "品牌B": [
            ["序号", "设备名称", "品牌", "型号", "规格", "国别", "数量", "单位", "备注", "产品编码", "标底参数"],
            [1, "服务器", "戴尔", "SRV-300", "2U", "美国", 1, "台", "数据库", "DB300", "参数C"],
        ],
    }
    # 价格表：仅按「产品编码(物料编号)」定位——故意不带品牌/型号列，验证 code 关联
    # 1200000043 故意填错价格，验证被强制覆盖为 市场=15000/其余=9000
    prc = {
        "价格": [
            ["产品编码", "核心价(H)", "签约价(Q)", "大客户价(D)", "批发价(P)",
             "业务底价(Y)", "概算价", "销售指导价", "租赁价", "市场价"],
            ["HA100", 1000, "", "", 900, "", "", "", "", ""],   # 仅 H + 批发价(导入)
            ["HA200", "", 700, "", "", "", "", "", "", ""],            # 仅 Q
            ["DB300", "", "", "", "", "", 6000, 7000, 4000, 5000], # 市场 + 直接价
            ["1200000043", 111, 222, 333, 444, 555, 666, 777, 888],  # 故意错价，应被覆盖
        ],
    }
    # 报价表（含一个不在库的型号；第二页用于验证多页对应）
    quote = {
        "报价": [
            ["序号", "设备名称", "品牌", "型号", "规格", "国别", "数量", "单位", "备注", "标底参数"],
            [1, "防火墙", "华为", "FW-100", "1U", "中国", 2, "台", "核心网", "参数A"],
            [2, "交换机", "华为", "SW-200", "24口", "中国", 5, "台", "", "参数B"],
            [3, "服务器", "戴尔", "SRV-300", "2U", "美国", 1, "台", "数据库", "参数C"],
            [4, "未知设备", "思科", "XXXX", "?", "美国", 3, "台", "", "参数X"],
        ],
        "报价二": [
            ["序号", "设备名称", "品牌", "型号", "规格", "国别", "数量", "单位", "备注", "标底参数"],
            [1, "防火墙", "华为", "FW-100", "1U", "中国", 1, "台", "第二页", "参数A"],
            [2, "未知设备", "思科", "XXXX", "?", "美国", 2, "台", "第二页", "参数X"],
        ],
    }
    _wb(os.path.join(C.SAMPLES_DIR, "配单表.xlsx"), cfg)
    plain_price = os.path.join(C.SAMPLES_DIR, "价格表.xlsx")
    _wb(plain_price, prc)
    _wb(os.path.join(C.SAMPLES_DIR, "报价表.xlsx"), quote)

    # 加密价格表：用默认密码加密上面的「价格表」字节（敏捷加密）
    enc = os.path.join(C.SAMPLES_DIR, "价格表_加密.xlsx")
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
        tmp = tf.name
    _wb(tmp, prc)
    DEC._encrypt_agile(tmp, enc, C.PRICE_FILE_PASSWORD)
    os.remove(tmp)
    print("  →", enc, f"（敏捷加密，密码 {C.PRICE_FILE_PASSWORD}）")

    # 标准加密价格表（CFB 容器，模拟真实「带密码测试.xlsx」那类）
    std_enc = os.path.join(C.SAMPLES_DIR, "价格表_标准加密.xlsx")
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
        tmp = tf.name
    _wb(tmp, prc)
    with open(tmp, "rb") as f:
        plain = f.read()
    std_bytes = _encrypt_standard(plain, C.PRICE_FILE_PASSWORD)
    with open(std_enc, "wb") as f:
        f.write(std_bytes)
    os.remove(tmp)
    print("  →", std_enc, f"（标准加密(CFB)，密码 {C.PRICE_FILE_PASSWORD}）")


if __name__ == "__main__":
    make()
