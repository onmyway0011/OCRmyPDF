#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OCRmyPDF 网页配置化工具
基于Streamlit构建的OCRmyPDF图形化界面

优化功能：
- 增强错误处理和日志记录
- 配置验证和预设模板
- 实时进度显示
- 批量文件处理
- 改进的临时文件管理
"""

import os
import sys
import subprocess
import tempfile
import logging
import time
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

import streamlit as st
import pikepdf

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置预设模板
CONFIG_PRESETS = {
    "文档扫描": {
        "mode": "normal",
        "language": "chi_sim",
        "deskew": True,
        "clean": True,
        "output_type": "pdfa",
        "optimize": "2"
    },
    "图书扫描": {
        "mode": "normal",
        "language": "chi_sim",
        "deskew": True,
        "clean": True,
        "rotate_pages": True,
        "output_type": "pdfa",
        "optimize": "3"
    },
    "英文文档": {
        "mode": "normal",
        "language": "eng",
        "output_type": "pdfa",
        "optimize": "1"
    },
    "混合语言": {
        "mode": "normal",
        "language": "eng+chi_sim",
        "output_type": "pdfa",
        "optimize": "2"
    },
    "强制重新OCR": {
        "mode": "force-ocr",
        "language": "chi_sim",
        "output_type": "pdfa",
        "optimize": "2"
    },
    "跳过文本页面": {
        "mode": "skip-text",
        "language": "chi_sim",
        "output_type": "pdfa",
        "optimize": "2"
    }
}

@contextmanager
def temp_file_manager(*files):
    """临时文件管理器"""
    try:
        yield
    finally:
        for file_path in files:
            try:
                if Path(file_path).exists():
                    os.unlink(file_path)
                    logger.info(f"清理临时文件: {file_path}")
            except Exception as e:
                logger.warning(f"清理临时文件失败 {file_path}: {e}")

def validate_config(config: Dict[str, Any]) -> List[str]:
    """验证配置参数"""
    errors = []
    
    if config.get('image_dpi', 300) < 72 or config.get('image_dpi', 300) > 600:
        errors.append("DPI值应在72-600之间")
    
    if config.get('jobs', 1) < 1 or config.get('jobs', 1) > os.cpu_count():
        errors.append(f"线程数应在1-{os.cpu_count()}之间")
    
    if config.get('jpeg_quality', 75) < 1 or config.get('jpeg_quality', 75) > 100:
        errors.append("JPEG质量应在1-100之间")
    
    return errors

def check_pdf_has_text(file_data: bytes) -> bool:
    """检测PDF是否已包含文本"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(file_data)
            tmp_file.flush()
            
            with pikepdf.open(tmp_file.name) as pdf:
                for page_num, page in enumerate(pdf.pages[:3]):  # 只检查前3页
                    try:
                        # 尝试提取文本
                        if '/Contents' in page:
                            # 简单检测是否有文本内容
                            contents = str(page.get('/Contents', ''))
                            if 'Tj' in contents or 'TJ' in contents or 'Td' in contents:
                                return True
                    except Exception:
                        continue
                        
            os.unlink(tmp_file.name)
            return False
    except Exception as e:
        logger.warning(f"检测PDF文本时出错: {e}")
        return False

# 页面配置
st.set_page_config(
    page_title="OCRmyPDF 网页工具",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    color: #1f77b4;
    text-align: center;
    margin-bottom: 2rem;
}
.section-header {
    font-size: 1.2rem;
    color: #2e8b57;
    margin-top: 1rem;
    margin-bottom: 0.5rem;
}
.info-box {
    background-color: #f0f8ff;
    padding: 1rem;
    border-radius: 0.5rem;
    border-left: 4px solid #1f77b4;
    margin: 1rem 0;
}
</style>
""", unsafe_allow_html=True)

# 主标题
st.markdown('<h1 class="main-header">📄 OCRmyPDF 网页配置工具</h1>', unsafe_allow_html=True)

# 侧边栏配置
with st.sidebar:
    st.markdown("### ⚙️ 配置选项")
    
    # 预设模板
    st.markdown('<div class="section-header">📋 预设模板</div>', unsafe_allow_html=True)
    
    preset_choice = st.selectbox(
        "选择预设配置",
        options=["自定义"] + list(CONFIG_PRESETS.keys()),
        help="选择预设配置模板，或选择自定义进行手动配置"
    )
    
    # 应用预设配置
    if preset_choice != "自定义":
        preset_config = CONFIG_PRESETS[preset_choice]
        st.info(f"✅ 已应用 '{preset_choice}' 预设配置")
    else:
        preset_config = {}
    
    # 基本设置
    st.markdown('<div class="section-header">🔧 基本设置</div>', unsafe_allow_html=True)
    
    mode_options = ["normal", "skip-text", "force-ocr", "redo-ocr"]
    mode_default = preset_config.get("mode", "normal")
    mode = st.selectbox(
        "处理模式",
        options=mode_options,
        index=mode_options.index(mode_default),
        format_func=lambda x: {
            "normal": "正常模式",
            "skip-text": "跳过文本页面", 
            "force-ocr": "强制OCR（覆盖已有文本）",
            "redo-ocr": "重新OCR"
        }[x],
        help="选择OCR处理模式。如果PDF已包含文本，建议选择'强制OCR'或'跳过文本页面'"
    )
    
    # 智能模式建议
    if mode == "normal":
        st.info("💡 提示：如果PDF已包含文本，处理可能失败。建议选择'强制OCR'模式。")
    
    lang_options = ["eng", "chi_sim", "chi_tra", "eng+chi_sim", "jpn", "kor", "fra", "deu", "spa"]
    lang_default = preset_config.get("language", "chi_sim")
    language = st.selectbox(
        "OCR语言",
        options=lang_options,
        index=lang_options.index(lang_default),
        format_func=lambda x: {
            "eng": "英文",
            "chi_sim": "中文简体",
            "chi_tra": "中文繁体",
            "eng+chi_sim": "英文+中文简体",
            "jpn": "日文",
            "kor": "韩文",
            "fra": "法文",
            "deu": "德文",
            "spa": "西班牙文"
        }[x],
        help="选择OCR识别语言"
    )
    
    pages = st.text_input(
        "指定页面",
        value="",
        help="指定要处理的页面，例如：1,3,5-10"
    )
    
    # 图像处理设置
    st.markdown('<div class="section-header">🖼️ 图像处理</div>', unsafe_allow_html=True)
    
    image_dpi = st.slider(
        "图像DPI",
        min_value=72,
        max_value=600,
        value=300,
        step=50,
        help="设置图像分辨率"
    )
    
    rotate_pages = st.checkbox("自动旋转页面", value=preset_config.get("rotate_pages", False), help="自动检测并旋转页面方向")
    deskew = st.checkbox("倾斜校正", value=preset_config.get("deskew", False), help="校正倾斜的页面")
    clean = st.checkbox("图像清理", value=preset_config.get("clean", False), help="OCR前清理图像")
    clean_final = st.checkbox("最终清理", value=preset_config.get("clean_final", False), help="最终输出前清理")
    
    # 输出设置
    st.markdown('<div class="section-header">📤 输出设置</div>', unsafe_allow_html=True)
    
    output_options = ["pdfa", "pdf", "pdfa-1", "pdfa-2", "pdfa-3"]
    output_default = preset_config.get("output_type", "pdfa")
    output_type = st.selectbox(
        "输出格式",
        options=output_options,
        index=output_options.index(output_default),
        format_func=lambda x: {
            "pdfa": "PDF/A (推荐)",
            "pdf": "标准PDF",
            "pdfa-1": "PDF/A-1",
            "pdfa-2": "PDF/A-2", 
            "pdfa-3": "PDF/A-3"
        }[x],
        help="选择输出PDF格式"
    )
    
    optimize_options = ["0", "1", "2", "3"]
    optimize_default = preset_config.get("optimize", "1")
    optimize = st.selectbox(
        "优化级别",
        options=optimize_options,
        index=optimize_options.index(optimize_default),
        format_func=lambda x: {
            "0": "无优化",
            "1": "轻度优化",
            "2": "中度优化",
            "3": "高度优化"
        }[x],
        help="选择PDF优化级别"
    )
    
    # 高级设置
    with st.expander("🔬 高级设置"):
        jobs = st.slider(
            "并行线程数",
            min_value=1,
            max_value=os.cpu_count() or 4,
            value=min(4, os.cpu_count() or 4),
            help="设置并行处理线程数"
        )
        
        jpeg_quality = st.slider(
            "JPEG质量",
            min_value=1,
            max_value=100,
            value=75,
            help="设置JPEG图像质量"
        )
        
        png_quality = st.slider(
            "PNG质量",
            min_value=1,
            max_value=100,
            value=75,
            help="设置PNG图像质量"
        )

# 配置验证
current_config = {
    'image_dpi': image_dpi,
    'jobs': jobs,
    'jpeg_quality': jpeg_quality,
    'png_quality': png_quality
}

config_errors = validate_config(current_config)
if config_errors:
    st.sidebar.error("⚠️ 配置错误:")
    for error in config_errors:
        st.sidebar.error(f"• {error}")

# 主内容区域
col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("### 📁 文件上传")
    
    # 批量处理选项
    batch_mode = st.checkbox("🔄 批量处理模式", help="同时处理多个文件")
    
    if batch_mode:
        uploaded_files = st.file_uploader(
            "选择多个PDF文件或图像文件",
            type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"],
            accept_multiple_files=True,
            help="支持PDF、PNG、JPG、TIFF、BMP格式，可选择多个文件"
        )
        uploaded_file = uploaded_files[0] if uploaded_files else None
    else:
        uploaded_file = st.file_uploader(
            "选择PDF文件或图像文件",
            type=["pdf", "png", "jpg", "jpeg", "tiff", "bmp"],
            help="支持PDF、PNG、JPG、TIFF、BMP格式"
        )
        uploaded_files = [uploaded_file] if uploaded_file else []
    
    if uploaded_file is not None:
        # 显示文件信息
        file_details = {
            "文件名": uploaded_file.name,
            "文件大小": f"{uploaded_file.size / 1024 / 1024:.2f} MB",
            "文件类型": uploaded_file.type
        }
        
        st.markdown("#### 📋 文件信息")
        for key, value in file_details.items():
            st.write(f"**{key}:** {value}")
        
        # 如果是PDF文件，显示元数据和智能检测
        if uploaded_file.name.lower().endswith('.pdf'):
            try:
                file_data = uploaded_file.getvalue()
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(file_data)
                    tmp_file.flush()
                    
                    with pikepdf.open(tmp_file.name) as pdf:
                        st.markdown("#### 📄 PDF信息")
                        
                        # 基本信息
                        st.write(f"**页数:** {len(pdf.pages)}")
                        
                        # 智能文本检测
                        has_text = check_pdf_has_text(file_data)
                        if has_text:
                            st.warning("⚠️ **检测到文本层**：此PDF已包含文本内容")
                            st.info("💡 **建议**：选择'强制重新OCR'或'跳过文本页面'预设模板")
                        else:
                            st.success("✅ **纯图像PDF**：未检测到文本层，可以正常OCR处理")
                        
                        # 元数据编辑
                        with st.expander("✏️ 编辑元数据"):
                            try:
                                with pdf.open_metadata() as meta:
                                    title = st.text_input("标题", value=meta.get('dc:title', ''))
                                    author = st.text_input("作者", value=meta.get('dc:creator', ''))
                                    subject = st.text_input("主题", value=meta.get('dc:description', ''))
                                    keywords = st.text_input("关键词", value=meta.get('dc:subject', ''))
                            except Exception as e:
                                st.warning(f"无法读取元数据: {e}")
                                title = author = subject = keywords = ""
                        
                os.unlink(tmp_file.name)
            except Exception as e:
                st.error(f"处理PDF文件时出错: {e}")
                title = author = subject = keywords = ""
        else:
            title = author = subject = keywords = ""

with col2:
    st.markdown("### ℹ️ 使用说明")
    
    st.markdown("""
    <div class="info-box">
    <h4>🚀 快速开始</h4>
    <ol>
    <li>上传PDF或图像文件</li>
    <li>在左侧配置OCR参数</li>
    <li>点击"开始处理"按钮</li>
    <li>等待处理完成并下载结果</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box">
    <h4>💡 提示</h4>
    <ul>
    <li>中文文档建议选择"中文简体"或"英文+中文简体"</li>
    <li>扫描质量较差的文档可以启用"图像清理"</li>
    <li>PDF/A格式适合长期存档</li>
    <li>优化级别越高，文件越小但处理时间越长</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

def process_single_file(file, args, progress_callback=None):
    """处理单个文件"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}") as input_file:
            input_file.write(file.getvalue())
            input_file.flush()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix="_ocr.pdf") as output_file:
                file_args = args + [input_file.name, output_file.name]
                
                if progress_callback:
                    progress_callback("🔄 正在启动OCR处理...", 10)
                
                logger.info(f"开始处理文件: {file.name}")
                logger.info(f"执行命令: {' '.join(file_args)}")
                
                process = subprocess.Popen(
                    file_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    universal_newlines=True
                )
                
                if progress_callback:
                    progress_callback("🔄 OCR处理中，请稍候...", 50)
                
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    if progress_callback:
                        progress_callback("✅ OCR处理完成！", 90)
                    
                    if Path(output_file.name).exists() and Path(output_file.name).stat().st_size > 0:
                        with open(output_file.name, "rb") as f:
                            output_data = f.read()
                        
                        logger.info(f"文件处理成功: {file.name}")
                        return output_data, None
                    else:
                        error_msg = "未生成输出文件"
                        logger.error(f"处理失败: {error_msg}")
                        return None, error_msg
                else:
                     error_msg = f"OCR处理失败 (退出码: {process.returncode})\n{stderr}"
                     logger.error(f"处理失败: {error_msg}")
                     
                     # 智能错误处理建议
                     if "PriorOcrFoundError" in stderr or "page already has text" in stderr:
                         error_msg += "\n\n💡 解决方案：\n" \
                                     "• 该PDF已包含文本层\n" \
                                     "• 请选择'强制OCR（覆盖已有文本）'模式重新处理\n" \
                                     "• 或选择'跳过文本页面'模式跳过已有文本的页面"
                     elif "TesseractNotFoundError" in stderr:
                         error_msg += "\n\n💡 解决方案：\n" \
                                     "• Tesseract OCR引擎未安装或未找到\n" \
                                     "• 请确保已正确安装Tesseract OCR"
                     elif "language" in stderr.lower() and "not found" in stderr.lower():
                         error_msg += "\n\n💡 解决方案：\n" \
                                     "• 所选语言包未安装\n" \
                                     "• 请安装相应的Tesseract语言包"
                     
                     return None, error_msg
                    
    except Exception as e:
        error_msg = f"处理过程中发生错误: {str(e)}"
        logger.exception(f"处理异常: {error_msg}")
        return None, error_msg
    finally:
        # 清理临时文件
        try:
            if 'input_file' in locals():
                os.unlink(input_file.name)
            if 'output_file' in locals() and Path(output_file.name).exists():
                os.unlink(output_file.name)
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")

# 处理按钮和结果显示
if uploaded_files:
    st.markdown("---")
    
    # 显示文件列表
    if batch_mode and len(uploaded_files) > 1:
        st.markdown(f"### 📋 待处理文件 ({len(uploaded_files)}个)")
        for i, file in enumerate(uploaded_files, 1):
            st.write(f"{i}. {file.name} ({file.size / 1024 / 1024:.2f} MB)")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        # 检查配置错误
        if config_errors:
            st.error("❌ 请先修复配置错误")
            st.stop()
        
        process_button_text = f"🚀 开始批量OCR处理 ({len(uploaded_files)}个文件)" if batch_mode and len(uploaded_files) > 1 else "🚀 开始OCR处理"
        
        if st.button(process_button_text, type="primary", use_container_width=True):
            # 构建命令行参数
             args = ["ocrmypdf"]
             
             # 添加各种参数
             if mode != "normal":
                 args.append(f"--{mode}")
             
             if language:
                 args.extend(["-l", language])
             
             if pages:
                 args.extend(["--pages", pages])
             
             if not uploaded_file.name.lower().endswith(".pdf") and image_dpi:
                 args.extend(["--image-dpi", str(image_dpi)])
             
             if rotate_pages:
                 args.append("--rotate-pages")
             
             if deskew:
                 args.append("--deskew")
             
             if clean:
                 args.append("--clean")
             
             if clean_final:
                 args.append("--clean-final")
             
             if output_type:
                 args.extend(["--output-type", output_type])
             
             if optimize != "0":
                 args.extend(["--optimize", optimize])
                 args.extend(["--jpeg-quality", str(jpeg_quality)])
                 args.extend(["--png-quality", str(png_quality)])
             
             if title:
                 args.extend(["--title", title])
             
             if author:
                 args.extend(["--author", author])
             
             if subject:
                 args.extend(["--subject", subject])
             
             if keywords:
                 args.extend(["--keywords", keywords])
             
             if jobs > 1:
                 args.extend(["--jobs", str(jobs)])
             
             # 处理文件
             if batch_mode and len(uploaded_files) > 1:
                 # 批量处理
                 st.markdown("### 📊 批量处理进度")
                 
                 overall_progress = st.progress(0)
                 overall_status = st.empty()
                 
                 results = []
                 errors = []
                 
                 for i, file in enumerate(uploaded_files):
                     overall_status.text(f"正在处理第 {i+1}/{len(uploaded_files)} 个文件: {file.name}")
                     
                     # 单文件进度
                     file_progress = st.progress(0)
                     file_status = st.empty()
                     
                     def progress_callback(status, progress):
                         file_status.text(status)
                         file_progress.progress(progress)
                     
                     output_data, error = process_single_file(file, args, progress_callback)
                     
                     if output_data:
                         results.append((file, output_data))
                         file_status.text(f"✅ {file.name} 处理完成")
                         file_progress.progress(100)
                     else:
                         errors.append((file.name, error))
                         file_status.text(f"❌ {file.name} 处理失败")
                         st.error(f"处理 {file.name} 时出错: {error}")
                     
                     overall_progress.progress((i + 1) / len(uploaded_files))
                 
                 overall_status.text(f"✅ 批量处理完成！成功: {len(results)}个，失败: {len(errors)}个")
                 
                 # 显示结果
                 if results:
                     st.success(f"🎉 成功处理 {len(results)} 个文件！")
                     
                     # 提供单独下载
                     for file, output_data in results:
                         output_filename = f"ocr_{file.name}"
                         if not output_filename.lower().endswith('.pdf'):
                             output_filename = f"{Path(file.name).stem}_ocr.pdf"
                         
                         st.download_button(
                             label=f"📥 下载 {file.name}",
                             data=output_data,
                             file_name=output_filename,
                             mime="application/pdf",
                             key=f"download_{file.name}"
                         )
                 
                 if errors:
                     st.error(f"❌ {len(errors)} 个文件处理失败")
                     for filename, error in errors:
                         st.error(f"• {filename}: {error}")
             
             else:
                 # 单文件处理
                 progress_bar = st.progress(0)
                 status_text = st.empty()
                 
                 def progress_callback(status, progress):
                     status_text.text(status)
                     progress_bar.progress(progress)
                 
                 output_data, error = process_single_file(uploaded_file, args, progress_callback)
                 
                 if output_data:
                     progress_bar.progress(100)
                     
                     output_filename = f"ocr_{uploaded_file.name}"
                     if not output_filename.lower().endswith('.pdf'):
                         output_filename = f"{Path(uploaded_file.name).stem}_ocr.pdf"
                     
                     st.success("🎉 OCR处理成功完成！")
                     
                     st.download_button(
                         label="📥 下载处理后的PDF",
                         data=output_data,
                         file_name=output_filename,
                         mime="application/pdf",
                         type="primary",
                         use_container_width=True
                     )
                     
                     # 显示文件大小对比
                     original_size = len(uploaded_file.getvalue()) / 1024 / 1024
                     output_size = len(output_data) / 1024 / 1024
                     
                     st.info(f"📊 文件大小: {original_size:.2f} MB → {output_size:.2f} MB")
                 else:
                      st.error(f"❌ 处理失败: {error}")

# 页脚
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; margin-top: 2rem;">
    <p>🔧 基于 <a href="https://github.com/ocrmypdf/OCRmyPDF" target="_blank">OCRmyPDF</a> 构建 | 
    💻 使用 <a href="https://streamlit.io" target="_blank">Streamlit</a> 开发</p>
</div>
""", unsafe_allow_html=True)