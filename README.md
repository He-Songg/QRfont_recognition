# 二维码 PDF 扫描提取工具

本工具用于读取由二维码组成的 PDF（每个二维码代表一个字符），输出原始文本（UTF-8），并尽可能保留原段落的换行。
字体来源：[xiaosongQRfont](https://github.com/hnzxs/xiaosongQRfont)。

## 工作原理
- 优先直接从 PDF 解析文本（若 PDF 内嵌真实文本层则直接使用）。
- 若解析不到文本，则将页面渲染为图像并用 OpenCV 的 QRCodeDetector 进行多二维码检测与解码。
- 通过二维码位置按 Y 方向聚类恢复行序，按 X 排序还原字符顺序。
- 需人工在段位添加加号“+”，以辅助程序识别自然段，输出时会自动将加号输出为换行符，无其他换行的情况。

## 依赖
- Python 3.9+
- PyMuPDF
- opencv-python
- numpy

## 安装
在项目目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使用
默认输入文件为当前目录的 `测试文档.pdf`，默认输出为 `result_YYMMDD_hhmmss.txt`：

```bash
python main.py
```

也可显式指定输入与输出路径：

```bash
python main.py /path/to/input.pdf /path/to/output.txt
```

可调整渲染倍率（与二维码尺寸相关，默认 4.0）：

```bash
python main.py 二维码测试.pdf result.txt --zoom 4.0
```

## 常见问题
- 如果报错提示缺少依赖，请先按上面的“安装”步骤安装依赖。
- 若输出为空或乱码，可尝试增大 `--zoom`（如 5~6），或确保 PDF 并非扫描件（位图二维码也支持，但过小会影响识别）。
