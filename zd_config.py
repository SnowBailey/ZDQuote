"""ZD 报价助手 - 全局配置与常量。"""
import os
import sys

# ---- 自适应线程数（依据本机 CPU 核心，适配 M1/M2/M3/M4）----
def cpu_workers(default: int = 4, cap: int = 8) -> int:
    """返回并行清洗建议线程数：取物理核心数并封顶，避免 GIL 争用。

    M 系列芯片性能/能效核较多，全部拉满反而因 GIL 互相掣肘；
    经验封顶 8 线程即可在多数机型上跑满 I/O 与解析收益。
    """
    n = None
    try:
        n = os.process_cpu_count()  # 3.13+ 优先用物理核心
    except Exception:
        n = None
    if n is None:
        n = os.cpu_count() or default
    return max(1, min(int(n), cap))


# ---- 路径 ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 打包成 .app 后，__file__ 位于只读的 app 包内，不能往里写数据库/报价单。
# 因此 frozen 运行时把数据重定向到用户目录（~/Documents/ZDQuote），可写且易查找。
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "ZDQuote")

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SAMPLES_DIR = os.path.join(BASE_DIR, "samples")
DB_PATH = os.path.join(DATA_DIR, "zd.db")
for _d in (DATA_DIR, OUTPUT_DIR):
    os.makedirs(_d, exist_ok=True)

# ---- 价格体系（UI 标签 -> 数据库列名，用于报价时选体系）----
PRICE_SYSTEMS = {
    "核心价（H价）": "h_price",
    "签约价（Q价）": "q_price",
    "大客户价（D价）": "d_price",
    "批发价（P价）": "p_price",
    "业务底价（Y价）": "y_price",
    "概算价": "budget_price",
    "销售指导价": "sale_guide_price",
    "租赁价": "lease_price",
    "市场价": "market_price",
}
# 全部价格字段（数据库列），用于清洗数值化 / 合并 / 导出
PRICE_RAW_FIELDS = [
    "h_price", "q_price", "d_price", "p_price", "y_price",
    "budget_price", "sale_guide_price", "lease_price", "market_price",
]
# 直接价：仅按导入填写，缺失不推算
DIRECT_PRICES = {"budget_price", "sale_guide_price", "lease_price"}
# 派生价：导入有则保留，缺失按 Y 基准推算（向上取整）
DERIVED_PRICES = {"h_price", "q_price", "d_price", "p_price",
                  "y_price", "market_price"}
PRICE_COLUMNS = list(PRICE_SYSTEMS.values())

# ---- 字段同义词（小写、去空格后做“包含”匹配，最长优先）----
FIELD_SYNONYMS = {
    "seq":       ["序号", "编号", "no.", "no"],
    "name":      ["设备名称", "设备名", "设备", "名称", "品名", "货物名称", "产品名称"],
    "brand":     ["品牌"],
    "model":     ["规格型号", "型号", "型"],
    "spec":      ["规格", "技术规格", "参数规格"],
    "country":   ["国别", "国家", "产地", "原产国"],
    "qty":       ["数量", "台数", "数目", "采购数量"],
    "unit":      ["单位", "计量单位"],
    "remark":    ["备注", "注释", "说明"],
    "code":      ["产品编码", "物料编码", "货号", "编码", "物料号", "物料编号"],
    "bid_param": ["标底参数", "标底", "招标参数", "招标技术参数"],
    "h_price":   ["h价", "h单价", "h价格", "核心价"],
    "q_price":   ["q价", "q单价", "q价格", "签约价"],
    "d_price":   ["d价", "d单价", "d价格", "大客户价"],
    "p_price":   ["p价", "p单价", "p价格", "批发价"],
    "y_price":   ["y价", "y单价", "y价格", "业务底价"],
    "market_price": ["市场价", "市场价格", "市价"],
    "budget_price": ["概算价", "概算", "估算价"],
    "sale_guide_price": ["销售指导价", "销售价", "指导售价"],
    "lease_price": ["租赁价", "租赁", "租金"],
}

# 价格推导链：以「业务底价 Y」为基准（price = Y × factor）
# H = Y×0.63，Q = Y×0.7，D = Y×0.8，市场 = Y×2
# 基准优先级：Y 优先；Y 缺则用 D（D = Y×0.8 → Y = D/0.8）；
# 两者皆缺则从 H/Q/市场 反推 Y。p_price（批发价）无给定系数，仅按导入填写。
PRICE_FACTORS = {
    "h_price": 0.63,
    "q_price": 0.7,
    "d_price": 0.8,
    "y_price": 1.0,
    "market_price": 2.0,
}

# 默认价格表密码（Excel 加密，ECMA-376 Agile 标准加密）
PRICE_FILE_PASSWORD = "EZpro2026"

# 特殊物料编码的「强制价格覆盖」：命中后无视价格表导入值，统一按此设定。
# 1200000043：市场价 = 15000，其余 8 类价格（H/Q/D/P/Y/概算/销售指导/租赁）统一 = 9000
SPECIAL_PRICE_OVERRIDE = {
    "1200000043": {
        **{k: 9000 for k in PRICE_RAW_FIELDS if k != "market_price"},
        "market_price": 15000,
    },
}

# 输出报价单列顺序
OUTPUT_COLUMNS = [
    ("seq", "序号"),
    ("name", "设备名称"),
    ("brand", "品牌"),
    ("model", "型号"),
    ("spec", "规格"),
    ("country", "国别"),
    ("qty", "数量"),
    ("unit", "单位"),
    ("price", "单价"),
    ("he", "合价"),
    ("remark", "备注"),
    ("bid_param", "标底参数"),
]
