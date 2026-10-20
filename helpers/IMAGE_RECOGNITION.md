# 颜色敏感图像测试

`he_image_recognition.ImageRecognitionHelper` 用于截图、产品导出图片和热成像
伪彩色图的颜色回归测试。它比较指定区域的逐像素颜色，也可以测量目标颜色的面积占比。
旧的 `he_image_handling.ImageHelper` 与 GUI/OCR 调用保持不变。

安装可选依赖（仓库根目录）：

```powershell
python -m pip install -e "./embedded_test_framework[image]"
```

## 与合格参考图比较

```python
from embedded_test_framework.helpers.he_image_recognition import ImageRecognitionHelper

helper = ImageRecognitionHelper()
result = helper.compare(
    "captured.png", "approved_reference.png",
    roi=(100, 80, 500, 380),
    delta_e_tolerance=2.0,
)
# 数值仅演示 API，并非产品验收标准。
result.mismatch_mask.save("color_mismatch.png")
result.assert_match(min_matched_fraction=0.995)
print(result.mean_delta_e, result.max_delta_e, result.p95_delta_e)
```

ROI 为 `(left, top, right, bottom)`，右/下边界不包含；不传则比较全图。
输入接受文件路径、Pillow 图像或 `uint8` 的 `(高, 宽, 3)` RGB 数组。
OpenCV 的 BGR 数组需调用方先转为 RGB。两张图必须同尺寸、同位置；不自动缩放、
对齐、平滑、白平衡或亮度归一化，避免掩盖产品缺陷。

算法使用 [scikit-image 的 CIEDE2000 和 sRGB→Lab 转换](https://scikit-image.org/docs/stable/api/skimage.color.html#skimage.color.deltaE_ciede2000)。
逐像素色差小于等于 `delta_e_tolerance` 为匹配；`matched_fraction` 范围为 0～1。
结果同时包含均值、最大值、95 分位色差及参与比较的像素数，避免只看均值漏掉局部异常。
`mismatch_mask` 是 ROI 大小的灰度图，白色为超差像素，黑色为匹配或排除像素；
`mismatch_mask.getbbox()` 可取得异常区域的包围框，坐标相对 ROI 左上角。

## 色块、调色板或特定颜色区域

### 摄像头帧中的红、绿、蓝色区域定位

当需求是“找到哪一块是绿色/红色/蓝色”，使用 `find_color_regions()`。
它按 HSV 色相、饱和度、亮度筛选像素，再找出连续色块；不要求颜色恰好等于纯红/绿/蓝。
算法复用 [scikit-image 的 RGB→HSV 转换](https://scikit-image.org/docs/stable/api/skimage.color.html#skimage.color.rgb2hsv)。

```python
from embedded_test_framework.helpers.he_image_recognition import ImageRecognitionHelper

helper = ImageRecognitionHelper()
# camera 是调用方已经打开的 OpenCV VideoCapture；此 helper 不负责打开摄像头。
ok, frame_bgr = camera.read()
if not ok or frame_bgr is None:
    raise RuntimeError("摄像头取帧失败")
frame_rgb = frame_bgr[:, :, ::-1]  # 仅用于 BGR 帧；相机 SDK 已返回 RGB 时不要反转。

for color in ("red", "green", "blue"):
    patches = helper.find_color_regions(frame_rgb, color, min_area=100)
    assert patches, f"未检测到 {color} 区域"
    for patch in patches:
        print(patch.color, patch.bbox, patch.pixel_count)
```

返回值为 `list[ColorRegion]`，按匹配像素面积从大到小排序；没找到返回空列表。
`bbox` 是完整输入图像上的 `(left, top, right, bottom)`，右/下边界不包含；
`pixel_count` 是该连续区域实际匹配的像素数，并非包围框面积。上下左右相邻的
像素算连续，仅对角接触的像素属于不同区域。`min_area` 过滤小块噪点。

已知产品某一部分应为绿色时，可限定区域：

```python
green = helper.find_color_regions(
    frame_rgb, "green", roi=(100, 80, 300, 280), min_area=100,
    min_saturation=0.35, min_value=0.2,
)
# 示例：该 200×200 区域至少有 80% 的像素属于保留下来的绿色色块。
assert sum(p.pixel_count for p in green) / (200 * 200) >= 0.8
```

默认色相范围（单位为度，包含端点）为红色 345～360 或 0～15、绿色 75～165、
蓝色 195～255；默认最低饱和度 0.35、最低亮度 0.2，均可调整。
`hue_range=(起点, 终点)` 可覆盖默认色相范围；起点大于终点表示跨越 0°。
纯黑/灰/白不具有有效色相，即使两个最低阈值设为零也不会被识别成彩色色块。
这些默认值是初始识别参数，需用相机实际曝光、白平衡和光照条件下的样本校准。

`roi` 和 `mask` 用法与图片比较相同，会先裁切/排除再划分连续区域。
背景中的同色物体也会被检测到；此方法不识别产品身份，应使用 ROI/mask 限定主体。
压缩视频、JPEG 字节、Bayer/YUV 原始帧需先由相机 SDK 解码成 RGB uint8 图像。
这里逐帧处理，不包含摄像头驱动、取流、跟踪或实时帧率保证，也不新增 OpenCV 依赖。

### 与精确标准颜色比较

```python
result = helper.match_color(
    "palette.png", expected_rgb=(255, 0, 0),
    roi=(0, 0, 20, 100), delta_e_tolerance=2.0,
)
result.assert_match(0.99)
```

对色条的每个已知色块分别选择 ROI 与标准 RGB 进行比较。对于热成像画面，
也可用此接口测量某一指定颜色的占比，但这并不等于真实的高温区域占比。

动态文字、时间戳、十字标记可通过布尔 `mask` 排除。mask 必须与完整图像同高宽，
True 表示参与比较；同时传 ROI 时取两者交集，空选区会报错：

```python
import numpy as np

mask = np.ones((480, 640), dtype=bool)
mask[:40, :] = False
result = helper.compare("captured.png", "approved_reference.png", delta_e_tolerance=2, mask=mask)
result.assert_match(0.995)
```

## 颜色管理与验收边界

- 带嵌入 ICC 的图片通过 Pillow 转为 8-bit sRGB；无 ICC 的图片及数组按 sRGB 解释。
  转换采用相对色度意图。损坏的 ICC 会报错，不静默忽略。
- 接受 RGB、不透明 RGBA 和调色板图片；透明图片需先按实际背景合成。
  不接受灰度/16-bit/浮点原始数据，避免把温度数据或高位深数据悄悄压成 8-bit。
- 这衡量的是图像编码后的颜色差异；8-bit 量化和 sRGB 色域限制不适合作为广色域、
  HDR 或显示器物理色度计量的替代。拍摄屏幕/实物时需固定曝光、白平衡、照明、
  拍摄位置并校准相机，截图本身也不能验证屏幕面板的实际出光颜色。
- 热成像参考图需固定调色板、显示温区/自动量程策略和采集条件；场景变化会改变
  伪彩色分布。绝对测温准确度需要原始辐射/温度数据、发射率等标定信息和温度基准，
  不能仅凭一张伪彩色图片判定。
- 用代表性的合格与不合格样本确定 ROI、色差阈值和通过占比。本工具不内置公司产品
  验收标准，也不包含 OCR、目标检测模型或自动温度反演。

验证：`python -m pytest embedded_test_framework/unittest/test_he_image_recognition.py -q`。
未安装 image 可选依赖时，此测试模块跳过。
