"""ZD 报价助手 - 价格推导逻辑。

规则（依据最新需求）：
1. 直接价（概算价 / 销售指导价 / 租赁价）：导入有则保留原值，缺失不推算（留空）。
2. 派生价（核心价 H / 签约价 Q / 大客户价 D / 批发价 P / 业务底价 Y / 市场价）：
   导入有则保留原值；缺失按「业务底价 Y」为基准推算，并向上取整。
3. 基准 Y 的确定：
   - Y 已导入 → 直接作为基准；
   - Y 缺、D 已导入 → Y = ceil(D / 0.8)（因 D = Y×0.8）；
   - Y、D 皆缺 → 从 H / Q / 市场 反推 true Y（H/0.63、Q/0.7、市场/2），再向上取整作为基准。
4. 其余派生价 = ceil(基准 Y × 系数)；导入值保留，不覆盖。
   （即「D = ceil(Y×0.8)」等关系在取整后的基准上成立。）
5. 批发价（P）无给定系数，仅按导入填写，不参与推算。
6. 浮点保护：推算值减去 1e-9 再 ceil，避免 63.0000000001 之类被误判进位。
"""
import math
import zd_config as C


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("¥", "").replace("￥", "")
        if s == "":
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _ceil(v):
    """向上取整，并消除浮点误差导致的误进位。"""
    return math.ceil(v - 1e-9)


def derive_prices(raw: dict) -> dict:
    """raw 键为 zd_config.PRICE_RAW_FIELDS 中的价格字段（值或 None）。

    返回相同键的推导结果：直接价原样保留（缺失留空），
    派生价缺失项按 Y 基准推算并向上取整。
    """
    vals = {k: _to_float(raw.get(k)) for k in C.PRICE_RAW_FIELDS}
    out = {k: vals[k] for k in C.PRICE_RAW_FIELDS}

    # 直接价：原样保留（不推算），仅当导入为空时留 None
    for k in C.DIRECT_PRICES:
        out[k] = vals[k]

    # ---- 确定基准 Y（取整后的 Y 基准）----
    y_base = None
    if vals["y_price"] is not None:
        y_base = vals["y_price"]                 # 导入的 Y 直接作为基准
    elif vals["d_price"] is not None:
        y_base = _ceil(vals["d_price"] / C.PRICE_FACTORS["d_price"])  # D/0.8
    else:
        true_y = None
        for src, fac in (("h_price", C.PRICE_FACTORS["h_price"]),
                         ("q_price", C.PRICE_FACTORS["q_price"]),
                         ("market_price", C.PRICE_FACTORS["market_price"])):
            if vals[src] is not None:
                true_y = vals[src] / fac
                break
        if true_y is None:
            return out  # 无任何可推导基准，派生价保持导入（或空）
        y_base = _ceil(true_y)

    # ---- 以 y_base 为基准，补齐缺失的派生价（导入值保留，不覆盖）----
    for k in C.DERIVED_PRICES:
        if k == "p_price":
            continue  # 批发价无系数，仅按导入
        if out.get(k) is None:
            fac = C.PRICE_FACTORS.get(k)
            if fac is None:
                continue
            out[k] = _ceil(y_base * fac)
    return out


if __name__ == "__main__":
    # 自测
    print("仅 H=100:", derive_prices({"h_price": 100}))
    # Y=ceil(100/0.63)=159; Q=112; D=ceil(159*0.8)=128; 市场=318
    print("仅 D=80 :", derive_prices({"d_price": 80}))
    # Y=ceil(80/0.8)=100; H=63; Q=70; 市场=200
    print("直接价+市场:", derive_prices(
        {"budget_price": 500, "sale_guide_price": 600, "market_price": 230}))
    # Y=ceil(230/2)=115; H=73; Q=81; D=92; 概算/销售指导原样
    print("全部为空 :", derive_prices({}))
