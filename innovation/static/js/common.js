// 公共工具函数库

// 显示消息提示
function showMessage(message, type = 'info') {
    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';

    const alertHtml = `
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;

    // 移除现有的消息
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach(alert => alert.remove());

    // 添加新消息到页面顶部
    const container = document.querySelector('.container');
    container.insertAdjacentHTML('afterbegin', alertHtml);

    // 3秒后自动消失
    setTimeout(() => {
        const alert = document.querySelector('.alert');
        if (alert) {
            alert.remove();
        }
    }, 3000);
}

// 显示加载状态
function showLoading(element, text = '加载中...') {
    if (typeof element === 'string') {
        element = document.querySelector(element);
    }

    if (element) {
        element.innerHTML = `
            <div class="d-flex justify-content-center align-items-center p-3">
                <div class="spinner-border spinner-border-sm me-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                ${text}
            </div>
        `;
    }
}

// 隐藏加载状态
function hideLoading(element) {
    if (typeof element === 'string') {
        element = document.querySelector(element);
    }

    if (element) {
        element.innerHTML = '';
    }
}

// 格式化日期
function formatDate(dateString) {
    if (!dateString) return '-';

    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// 获取状态对应的Bootstrap颜色类
function getStatusColor(status) {
    const statusColors = {
        '待承接': 'warning',
        '进行中': 'info',
        '已完成': 'success',
        '已取消': 'secondary',
        '已拒绝': 'danger'
    };
    return statusColors[status] || 'secondary';
}

// 获取状态对应的图标
function getStatusIcon(status) {
    const statusIcons = {
        '待承接': 'clock',
        '进行中': 'gear',
        '已完成': 'check-circle',
        '已取消': 'x-circle',
        '已拒绝': 'exclamation-triangle'
    };
    return statusIcons[status] || 'question-circle';
}

// 文件大小格式化
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 验证表单
function validateForm(formElement) {
    const requiredFields = formElement.querySelectorAll('[required]');
    let isValid = true;

    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.classList.add('is-invalid');
            isValid = false;
        } else {
            field.classList.remove('is-invalid');
        }
    });

    return isValid;
}

// 清除表单验证状态
function clearFormValidation(formElement) {
    const fields = formElement.querySelectorAll('.is-invalid');
    fields.forEach(field => {
        field.classList.remove('is-invalid');
    });
}

// 重置表单
function resetForm(formElement) {
    formElement.reset();
    clearFormValidation(formElement);

    // 清除文件预览
    const previews = formElement.querySelectorAll('.image-preview');
    previews.forEach(preview => {
        preview.innerHTML = '';
    });
}

// 图片预览功能
function previewImage(input, previewContainer) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();

        reader.onload = function(e) {
            const preview = document.querySelector(previewContainer);
            if (preview) {
                preview.innerHTML = `
                    <div class="position-relative d-inline-block">
                        <img src="${e.target.result}" class="img-thumbnail" style="max-width: 200px; max-height: 200px;">
                        <button type="button" class="btn btn-sm btn-danger position-absolute top-0 end-0" 
                                onclick="removeImagePreview('${previewContainer}', '${input.id}')">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                `;
            }
        };

        reader.readAsDataURL(input.files[0]);
    }
}

// 多张图片预览功能
function previewMultipleImages(input, previewContainer) {
    const preview = document.querySelector(previewContainer);
    if (!preview) return;

    // 清空之前的预览
    preview.innerHTML = '';

    if (input.files && input.files.length > 0) {
        // 限制最多5张图片
        const maxFiles = 5;
        const files = Array.from(input.files).slice(0, maxFiles);

        if (input.files.length > maxFiles) {
            showMessage(`最多只能上传${maxFiles}张图片，已自动选择前${maxFiles}张`, 'warning');
        }

        files.forEach((file, index) => {
            // 检查文件大小（5MB限制）
            if (file.size > 5 * 1024 * 1024) {
                showMessage(`文件 ${file.name} 超过5MB限制，已跳过`, 'warning');
                return;
            }

            const reader = new FileReader();
            reader.onload = function(e) {
                const imageDiv = document.createElement('div');
                imageDiv.className = 'position-relative d-inline-block';
                imageDiv.innerHTML = `
                    <img src="${e.target.result}" class="img-thumbnail" style="max-width: 150px; max-height: 150px;">
                    <button type="button" class="btn btn-sm btn-danger position-absolute top-0 end-0" 
                            onclick="removeMultipleImagePreview(this, '${input.id}', ${index})">
                        <i class="bi bi-x"></i>
                    </button>
                `;
                preview.appendChild(imageDiv);
            };
            reader.readAsDataURL(file);
        });
    }
}

function previewMultipleVideos(input, previewContainer) {
    const preview = document.querySelector(previewContainer);
    if (!preview) return;

    const existingVideos = preview.querySelectorAll('video');
    existingVideos.forEach(v => {
        try {
            if (v.src && v.src.startsWith('blob:')) URL.revokeObjectURL(v.src);
        } catch {}
    });

    preview.innerHTML = '';

    if (input.files && input.files.length > 0) {
        const maxFiles = 2;
        const files = Array.from(input.files).slice(0, maxFiles);

        if (input.files.length > maxFiles) {
            showMessage(`最多只能上传${maxFiles}个视频，已自动选择前${maxFiles}个`, 'warning');
        }

        files.forEach((file, index) => {
            if (file.size > 100 * 1024 * 1024) {
                showMessage(`文件 ${file.name} 超过100MB限制，已跳过`, 'warning');
                return;
            }

            const url = URL.createObjectURL(file);
            const videoDiv = document.createElement('div');
            videoDiv.className = 'position-relative d-inline-block';
            videoDiv.innerHTML = `
                <video src="${url}" class="img-thumbnail" style="max-width: 240px; max-height: 150px; background: #000;" controls preload="metadata"></video>
                <button type="button" class="btn btn-sm btn-danger position-absolute top-0 end-0" 
                        onclick="removeMultipleVideoPreview(this, '${input.id}', ${index})">
                    <i class="bi bi-x"></i>
                </button>
            `;
            preview.appendChild(videoDiv);
        });
    }
}

// 移除单张图片预览
function removeImagePreview(previewContainer, inputId) {
    const preview = document.querySelector(previewContainer);
    const input = document.getElementById(inputId);

    if (preview) {
        preview.innerHTML = '';
    }

    if (input) {
        input.value = '';
    }
}

// 移除多张图片中的单张预览
function removeMultipleImagePreview(button, inputId, index) {
    const input = document.getElementById(inputId);
    if (!input || !input.files) return;

    // 创建新的FileList，排除被删除的文件
    const dt = new DataTransfer();
    const files = Array.from(input.files);

    files.forEach((file, i) => {
        if (i !== index) {
            dt.items.add(file);
        }
    });

    input.files = dt.files;

    // 重新预览剩余图片
    previewMultipleImages(input, '#imagePreview');
}

function removeMultipleVideoPreview(button, inputId, index) {
    const input = document.getElementById(inputId);
    if (!input || !input.files) return;

    const dt = new DataTransfer();
    const files = Array.from(input.files);

    files.forEach((file, i) => {
        if (i !== index) {
            dt.items.add(file);
        }
    });

    input.files = dt.files;

    previewMultipleVideos(input, '#videoPreview');
}

// 确认对话框
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// 安全关闭模态框
function closeModalSafely(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        const bootstrapModal = bootstrap.Modal.getInstance(modal);
        if (bootstrapModal) {
            bootstrapModal.hide();
        }
    }
}

// 复制到剪贴板
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showMessage('已复制到剪贴板', 'success');
    }).catch(() => {
        showMessage('复制失败', 'error');
    });
}

// 下载文件
function downloadFile(url, filename) {
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 节流函数
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 初始化所有工具提示
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 初始化所有弹出框
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // 自动关闭警告框
    setTimeout(() => {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(alert => {
            if (alert.classList.contains('auto-dismiss')) {
                alert.remove();
            }
        });
    }, 5000);
});

// 导出函数供其他脚本使用
window.InnovationApp = {
    showMessage,
    showLoading,
    hideLoading,
    formatDate,
    getStatusColor,
    getStatusIcon,
    formatFileSize,
    validateForm,
    clearFormValidation,
    resetForm,
    previewImage,
    previewMultipleImages,
    previewMultipleVideos,
    removeImagePreview,
    removeMultipleImagePreview,
    removeMultipleVideoPreview,
    confirmAction,
    closeModalSafely,
    copyToClipboard,
    downloadFile,
    debounce,
    throttle
};
