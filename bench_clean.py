"""清洗速度基准：旧 cell 随机访问法 vs 新 iter_rows 流式法。

生成写放大文件 -> 同文件两种方法计时 -> 打印加速比。
"""
import os
import sys
import time
import openpyxl
from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zd_excel as Z

HERE = os.path.dirname(os.path.abspath(__file__))
SMALL = os.path.join(HERE, "_bench_small.xlsx")   # 新旧对比用
LARGE = os.path.join(HERE, "_bench_large.xlsx")   # 仅新法展示大文件速度

HEADER = ["序号", "设备名称", "品牌", "型号", "规格", "国别", "数量", "单位",
          "备注", "产品编码", "标底参数", "H价", "Q价", "D价", "Y价",
          "市场价", "一档指导价"]


def make_file(path, sheets, rows_per):
    wb = Workbook()
    wb.remove(wb.active)
    for s in range(sheets):
        ws = wb.create_sheet(title=f"品牌{s+1}")
        ws.append(HEADER)
        for r in range(rows_per):
            ws.append([
                r + 1, f"设备{r+1}", f"品牌{s+1}", f"M{r+1}-{s}",
                "规格x", "中国", r + 1, "台", "备注", f"CODE{r}", "参数",
                100.0 + r, 70.0 + r, 80.0 + r, 63.0 + r, 50.0 + r, 158.0 + r,
            ])
    wb.save(path)
    print(f"  生成 {path}：{sheets} 页 x {rows_per} 行 = "
          f"{sheets*rows_per} 行")


# ---------- 旧法（复刻改动前的 cell 随机访问实现）----------
def _find_header_row_old(ws, max_scan=15):
    best_row, best_score = 1, -1
    for ri in range(1, min(ws.max_row, max_scan) + 1):
        cells = [ws.cell(row=ri, column=ci).value
                 for ci in range(1, ws.max_column + 1)]
        mp = Z._map_headers(cells)
        score = len(mp)
        if score > best_score:
            best_score, best_row = score, ri
    return best_row


def clean_old(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = []
    for name in wb.sheetnames:
        try:
            ws = wb[name]
        except KeyError:
            continue
        hrow = _find_header_row_old(ws)
        cells = [ws.cell(row=hrow, column=ci).value
                 for ci in range(1, ws.max_column + 1)]
        mp = Z._map_headers(cells)
        if not mp:
            continue
        for ri in range(hrow + 1, ws.max_row + 1):
            raw = {}
            for f, ci in mp.items():
                v = ws.cell(row=ri, column=ci + 1).value
                if v is None or (isinstance(v, str) and v.strip() == ""):
                    continue
                raw[f] = v
            if not raw:
                continue
            brand = str(raw.get("brand", "")).strip() or str(name)
            model = str(raw.get("model", "")).strip()
            if not model:
                continue
            raw["brand"], raw["model"] = brand, model
            out.append(raw)
    wb.close()
    return out


def main():
    t0 = time.perf_counter()
    if not os.path.exists(SMALL):
        make_file(SMALL, sheets=1, rows_per=300)   # 300 行（新旧对比用）
    if not os.path.exists(LARGE):
        make_file(LARGE, sheets=4, rows_per=3000)   # 12k 行
    print(f"  文件生成耗时 {time.perf_counter()-t0:.1f}s")

    print("\n[旧法 cell 随机访问] 小文件(300行) ...")
    t = time.perf_counter()
    old_rows = clean_old(SMALL)
    old_t = time.perf_counter() - t
    print(f"  旧法：{old_t:.2f}s，识别 {len(old_rows)} 行")

    print("[新法 iter_rows 流式] 同文件(300行) ...")
    t = time.perf_counter()
    new_rows = Z.read_workbook(SMALL, max_workers=1)
    new_t_small = time.perf_counter() - t
    print(f"  新法：{new_t_small:.2f}s，识别 {len(new_rows)} 行")

    print("[新法 iter_rows 流式] 24k 行 ...")
    t = time.perf_counter()
    big_rows = Z.read_workbook(LARGE, max_workers=1)
    new_t_big = time.perf_counter() - t
    print(f"  新法：{new_t_big:.2f}s，识别 {len(big_rows)} 行")

    print("\n========== 结论 ==========")
    if old_t > 0 and new_t_small > 0:
        print(f"同文件(12k行) 加速比：{old_t/new_t_small:.1f}x")
        print(f"旧法 {old_t:.2f}s -> 新法 {new_t_small:.2f}s")


if __name__ == "__main__":
    main()
