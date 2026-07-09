# -*- coding: utf-8 -*-
"""上传图像归一化 (审计 P0-2)。

空房照片来自手机/微信, 原样字节直存直传有四个坑:
  - 不验真身: 客户端 Content-Type 可伪造, 非图字节一路传到 provider 才炸;
  - EXIF Orientation: 浏览器显示正立, 但 provider 解码器不认 EXIF 时模型看到横竖颠倒的房间;
  - EXIF GPS: 业主住址坐标随请求原样外发第三方 relay (PIPL 红点);
  - 体积: 15MB 手机原图直传 relay 纯浪费上行。

归一化 = Pillow 验真身 -> exif_transpose 物化方向 -> 转 RGB -> 重编码 JPEG q90
(天然剥掉全部 EXIF 含 GPS) -> 最长边压 MAX_EDGE。产出稳定的 JPEG + 元数据
(width/height/mime/sha256), photos.json 与下游 size 选择都消费这些元数据。

HEIC (iPhone 默认格式) 经 pillow-heif 支持; 依赖缺失时优雅降级 (白名单不含 heic)。
"""
from __future__ import annotations

import hashlib
import io
import warnings

from PIL import Image, ImageFilter, ImageOps, ImageStat

from .errors import AIError

# 解压炸弹加固 (审查 PLAUSIBLE 项): 收紧像素上限并把"告警带"升级为异常 ——
# 一张 <15MB 高压缩 PNG 可解出上亿像素 (500MB+ 内存/请求)。上限 5000 万像素
# 对 2048 边长的目标绰绰有余; 超限 -> DecompressionBomb* -> normalize 归为 415。
Image.MAX_IMAGE_PIXELS = 50_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)

try:  # pillow-heif 为可选依赖: 缺失时 HEIC 上传 415, 其余格式不受影响。
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_SUPPORTED = True
except Exception:  # noqa: BLE001 - 导入失败仅降级能力, 不阻断服务。
    HEIF_SUPPORTED = False

# 最长边上限: 2048 对 gpt-image 输入绰绰有余, 且把 15MB 原图压到 ~几百 KB。
MAX_EDGE = 2048
JPEG_QUALITY = 90


THUMB_EDGE = 320
THUMB_QUALITY = 80

# 中等预览 (效果图页主图用): 全尺寸 render 是 ~2MB PNG, 直载慢; 1440px WEBP ~150-300KB,
# 屏显清晰, 全图只留下载。列表用 320 缩略图, 主图用 1440 预览, 下载用原 PNG (三级)。
PREVIEW_EDGE = 1440
PREVIEW_QUALITY = 82


def _resize_webp(data: bytes, max_edge: int, quality: int) -> bytes:
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((max_edge, max_edge), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=quality)
    return out.getvalue()


def make_thumb(data: bytes, *, max_edge: int = THUMB_EDGE) -> bytes:
    """产物/照片缩略图 (审计 P2-3): 320px WEBP, 列表页不再直载 1536 原 PNG / 手机原图。"""
    return _resize_webp(data, max_edge, THUMB_QUALITY)


def make_preview(data: bytes, *, max_edge: int = PREVIEW_EDGE) -> bytes:
    """效果图主预览: 1440px WEBP (~几百 KB), 页面主图用它而非 2MB 原 PNG。"""
    return _resize_webp(data, max_edge, PREVIEW_QUALITY)


def read_size(data: bytes) -> tuple[int, int]:
    """读图片真实 (width, height); 非图字节抛 AIError。

    P1: provider 返回图尺寸可能与请求尺寸不一致 (实测请求 1536x1024 -> 返回 1677x938)。
    出图后用它读回真实宽高写入 record 的 actual_size, 避免下游拿到错的 size 元数据。
    """
    try:
        with Image.open(io.BytesIO(data)) as img:
            return int(img.size[0]), int(img.size[1])
    except Exception as exc:  # noqa: BLE001 - Pillow 各类解码错误统一归为"非图像"
        raise AIError(f"无法读取图片尺寸 (损坏或不支持的格式): {exc}") from exc


# 照片质量评分 (工作流改造 B5): 确定性、纯 Pillow (无新依赖)。空房照质量直接决定 image2
# 结构复制的上限 —— 过暗/过曝/过小/极端广角/糊片会拉低出图上限。这里只做「尽力而为」的
# 轻量预警 (非阻断), 供前端展示可用性徽标, 引导用户换更好的底图。
_QUALITY_MIN_LONG_EDGE = 800   # 最长边 < 此 -> low_res (太小, 结构细节不足)
_QUALITY_MAX_ASPECT = 3.0      # 长短边比 > 此 -> extreme_aspect (广角全景/超竖幅畸变)
_QUALITY_DARK_MEAN = 40.0      # 平均亮度 < 此 -> too_dark
_QUALITY_BRIGHT_MEAN = 220.0   # 平均亮度 > 此 -> too_bright
_QUALITY_BLUR_STDDEV = 4.0     # 拉普拉斯响应 stddev < 此 -> blurry (细节/清晰度不足)
# 3x3 拉普拉斯核: 度量高频细节 (清晰度代理)。均匀/模糊图响应接近 0, 纹理清晰图响应大。
_LAPLACIAN = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=0)


def assess_quality(img: "Image.Image") -> dict:
    """对已归一化的 RGB 图评估质量, 返回 {score, warnings, brightness, sharpness, megapixels}。

    确定性: 同一图恒得同一结果。warnings ⊆ {low_res, extreme_aspect, too_dark, too_bright,
    blurry}; score = 100 - 25*len(warnings) (clamp 0)。水印/人物/遮挡检测需模型, 本批不做。"""
    w, h = img.size
    warnings: list[str] = []
    long_edge, short_edge = max(w, h), min(w, h)
    if long_edge < _QUALITY_MIN_LONG_EDGE:
        warnings.append("low_res")
    if short_edge > 0 and long_edge / short_edge > _QUALITY_MAX_ASPECT:
        warnings.append("extreme_aspect")
    gray = img.convert("L")
    brightness = ImageStat.Stat(gray).mean[0]
    if brightness < _QUALITY_DARK_MEAN:
        warnings.append("too_dark")
    elif brightness > _QUALITY_BRIGHT_MEAN:
        warnings.append("too_bright")
    # Pillow 的 Kernel 卷积会原样保留 1px 边框 (未卷积), 边框保留原亮度会污染 stddev ——
    # 裁掉边框只在有效卷积区上算清晰度 (否则纯色图会因边框≠内部而得到假高 stddev)。
    edges = gray.filter(_LAPLACIAN)
    ew, eh = edges.size
    if ew > 2 and eh > 2:
        edges = edges.crop((1, 1, ew - 1, eh - 1))
    sharpness = ImageStat.Stat(edges).stddev[0]
    if sharpness < _QUALITY_BLUR_STDDEV:
        warnings.append("blurry")
    return {
        "score": max(0, 100 - 25 * len(warnings)),
        "warnings": warnings,
        "brightness": round(brightness, 1),
        "sharpness": round(sharpness, 1),
        "megapixels": round(w * h / 1_000_000, 2),
    }


def normalize_photo(data: bytes) -> tuple[bytes, dict]:
    """归一化上传照片 -> (jpeg_bytes, meta)。非图像字节抛 AIError (路由映射 415)。"""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001 - Pillow 各类解码错误统一归为"非图像"
        raise AIError(f"无法解析图片 (损坏或不支持的格式): {exc}") from exc
    # 物化 EXIF 方向 (旋转像素本身), 之后任何不认 EXIF 的消费方都拿到正立图。
    transposed = ImageOps.exif_transpose(img)
    if transposed is not None:
        img = transposed
    if img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    # 质量评分在归一化后的图上算 (方向已物化、已压边), 与下游 image2 实际输入一致。
    # 尽力而为、非阻断: 评分失败降级为 None (与 make_thumb/make_preview 失败降级一致),
    # 绝不因质量评分让整个上传归一化 500。
    try:
        quality = assess_quality(img)
    except Exception:  # noqa: BLE001 - 质量评分是可选增强, 失败不阻断上传。
        quality = None
    out = io.BytesIO()
    # 重编码不带 exif 参数 => 全部 EXIF (含 GPS) 被剥离。
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    blob = out.getvalue()
    return blob, {
        "width": img.size[0],
        "height": img.size[1],
        "mime": "image/jpeg",
        "sha256": hashlib.sha256(blob).hexdigest(),
        "quality": quality,
    }
