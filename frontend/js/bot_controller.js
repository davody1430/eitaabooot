// frontend/js/bot_controller.js - مدیریت ربات‌ها
let currentBotId = null;
let isSending = false;
let sendStats = { total: 0, sent: 0, success: 0, error: 0 };

// ایجاد ربات جدید
async function createBot() {
    const botName = document.getElementById('botName').value || `bot_${Date.now()}`;
    const headless = document.getElementById('headlessMode').value === 'true';
    
    try {
        const response = await fetch(`${API_BASE_URL}/bot/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                bot_id: botName,
                headless: headless,
                min_delay: parseFloat(document.getElementById('minDelay').value),
                max_delay: parseFloat(document.getElementById('maxDelay').value)
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            currentBotId = data.bot_id;
            
            // نمایش اطلاعات ربات
            document.getElementById('botInfo').style.display = 'block';
            document.getElementById('currentBotId').textContent = currentBotId;
            document.getElementById('botStatus').textContent = 'آماده';
            
            showNotification('ربات با موفقیت ایجاد شد', 'success');
            
            // فعال کردن دکمه‌های لاگین
            document.getElementById('loginBtn').disabled = false;
        } else {
            showNotification(data.error || 'خطا در ایجاد ربات', 'error');
        }
    } catch (error) {
        showNotification('خطا در ارتباط با سرور', 'error');
        console.error(error);
    }
}

// شروع لاگین
async function startLogin() {
    if (!currentBotId) {
        showNotification('لطفاً ابتدا یک ربات ایجاد کنید', 'warning');
        return;
    }
    
    const phoneNumber = document.getElementById('phoneNumber').value.trim();
    
    // اعتبارسنجی شماره تلفن
    if (!phoneNumber.match(/^09\d{9}$/)) {
        showNotification('شماره تلفن باید با 09 شروع شود و 11 رقمی باشد', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/bot/${currentBotId}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone_number: phoneNumber })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            if (data.status === 'waiting') {
                showNotification('مرورگر باز شد. لطفاً کد تأیید را وارد کنید', 'info');
                document.getElementById('loginBtn').disabled = true;
                document.getElementById('confirmBtn').disabled = false;
                document.getElementById('loginStatus').innerHTML = 
                    '<div class="alert alert-info">در انتظار تأیید لاگین در مرورگر...</div>';
            } else {
                showNotification('لاگین موفقیت‌آمیز بود', 'success');
            }
        } else {
            showNotification(data.error || 'خطا در لاگین', 'error');
        }
    } catch (error) {
        showNotification('خطا در ارتباط با سرور', 'error');
        console.error(error);
    }
}

// تأیید لاگین
async function confirmLogin() {
    if (!currentBotId) {
        showNotification('ربات فعالی وجود ندارد', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/bot/${currentBotId}/confirm-login`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification('لاگین تأیید شد', 'success');
            document.getElementById('confirmBtn').disabled = true;
            document.getElementById('loginStatus').innerHTML = 
                '<div class="alert alert-success">✅ لاگین تأیید شد. می‌توانید ارسال را شروع کنید.</div>';
            document.getElementById('sendBtn').disabled = false;
        } else {
            showNotification(data.error || 'لاگین تأیید نشد', 'error');
        }
    } catch (error) {
        showNotification('خطا در تأیید لاگین', 'error');
        console.error(error);
    }
}

// شروع ارسال پیام‌ها
async function startSending() {
    if (!currentBotId) {
        showNotification('لطفاً ابتدا یک ربات ایجاد کنید', 'warning');
        return;
    }
    
    if (isSending) {
        showNotification('ارسال در حال انجام است', 'warning');
        return;
    }
    
    // جمع‌آوری داده‌ها
    const sendType = document.getElementById('sendType').value;
    const message = document.getElementById('messageToSend').value;
    
    if (!message.trim()) {
        showNotification('لطفاً متن پیام را وارد کنید', 'error');
        return;
    }
    
    const sendData = {
        type: sendType,
        message: message,
        min_delay: parseFloat(document.getElementById('minDelay').value),
        max_delay: parseFloat(document.getElementById('maxDelay').value)
    };
    
    // اضافه کردن داده‌های بر اساس نوع
    if (sendType === 'excel' || sendType === 'combined') {
        const excelFile = document.getElementById('excelFile').files[0];
        if (!excelFile) {
            showNotification('لطفاً فایل اکسل را انتخاب کنید', 'error');
            return;
        }
        // آپلود فایل و گرفتن مسیر
        const excelPath = await uploadExcelFile(excelFile);
        if (!excelPath) return;
        sendData.excel_path = excelPath;
    }
    
    if (sendType === 'group_message' || sendType === 'combined') {
        const groupName = document.getElementById('groupName').value;
        const messagePrefix = document.getElementById('messagePrefix').value;
        
        if (!groupName || !messagePrefix) {
            showNotification('لطفاً نام گروه و پیشوند پیام را وارد کنید', 'error');
            return;
        }
        
        sendData.group_name = groupName;
        sendData.message_prefix = messagePrefix;
    }
    
    // ریست آمار
    sendStats = { total: 0, sent: 0, success: 0, error: 0 };
    updateProgress(0);
    
    // شروع ارسال
    try {
        const response = await fetch(`${API_BASE_URL}/bot/${currentBotId}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sendData)
        });
        
        const data = await response.json();
        
        if (response.ok) {
            isSending = true;
            sendStats.total = data.total || 0;
            
            // فعال کردن دکمه توقف
            document.getElementById('stopBtn').disabled = false;
            document.getElementById('sendBtn').disabled = true;
            
            showNotification(`ارسال به ${data.total} مخاطب شروع شد`, 'success');
            
            // شروع بروزرسانی وضعیت
            startStatusUpdates();
        } else {
            showNotification(data.error || 'خطا در شروع ارسال', 'error');
        }
    } catch (error) {
        showNotification('خطا در ارتباط با سرور', 'error');
        console.error(error);
    }
}

// آپلود فایل اکسل
async function uploadExcelFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_BASE_URL}/contacts/upload`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            showNotification(data.message || 'فایل آپلود شد', 'success');
            return data.file_path || 'uploads/' + file.name;
        } else {
            showNotification(data.error || 'خطا در آپلود فایل', 'error');
            return null;
        }
    } catch (error) {
        showNotification('خطا در آپلود فایل', 'error');
        return null;
    }
}

// بروزرسانی وضعیت ارسال
function startStatusUpdates() {
    const updateInterval = setInterval(async () => {
        if (!isSending) {
            clearInterval(updateInterval);
            return;
        }
        
        try {
            // در اینجا می‌توانید وضعیت ارسال را از سرور بگیرید
            // فعلاً شبیه‌سازی می‌کنیم
            if (sendStats.sent < sendStats.total) {
                sendStats.sent += Math.floor(Math.random() * 3) + 1;
                sendStats.success += Math.floor(Math.random() * 2) + 1;
                sendStats.error = sendStats.sent - sendStats.success;
                
                if (sendStats.sent > sendStats.total) {
                    sendStats.sent = sendStats.total;
                }
                
                const progress = Math.round((sendStats.sent / sendStats.total) * 100);
                updateProgress(progress);
                
                // افزودن به لاگ
                addToLog(`ارسال ${sendStats.sent} از ${sendStats.total} (${sendStats.success} موفق)`);
            } else {
                // پایان ارسال
                isSending = false;
                clearInterval(updateInterval);
                document.getElementById('stopBtn').disabled = true;
                document.getElementById('sendBtn').disabled = false;
                
                showNotification('ارسال کامل شد', 'success');
                addToLog('✅ ارسال کامل شد');
            }
        } catch (error) {
            console.error('خطا در بروزرسانی وضعیت:', error);
        }
    }, 2000);
}

// توقف ارسال
async function stopSending() {
    if (!currentBotId) return;
    
    if (confirm('آیا می‌خواهید ارسال را متوقف کنید؟')) {
        isSending = false;
        document.getElementById('stopBtn').disabled = true;
        document.getElementById('sendBtn').disabled = false;
        
        showNotification('ارسال متوقف شد', 'info');
        addToLog('⏹️ ارسال توسط کاربر متوقف شد');
    }
}

// بروزرسانی نوع ارسال
function updateSendType() {
    const sendType = document.getElementById('sendType').value;
    
    document.getElementById('excelSection').style.display = 
        (sendType === 'excel' || sendType === 'combined') ? 'block' : 'none';
    
    document.getElementById('groupSection').style.display = 
        (sendType === 'group_message' || sendType === 'combined') ? 'block' : 'none';
}

// مدیریت فایل اکسل
function handleExcelFile(input) {
    const fileName = input.files[0] ? input.files[0].name : 'هیچ فایلی انتخاب نشده';
    document.getElementById('excelFileName').textContent = fileName;
}

// بروزرسانی نوار پیشرفت
function updateProgress(percentage) {
    const progressBar = document.getElementById('progressBar');
    const progressFill = progressBar.querySelector('.progress-fill');
    const progressText = document.getElementById('progressText');
    
    progressFill.style.width = percentage + '%';
    progressText.textContent = percentage + '%';
    
    // بروزرسانی آمار
    document.getElementById('sentCount').textContent = sendStats.sent;
    document.getElementById('successCount').textContent = sendStats.success;
    document.getElementById('errorCount').textContent = sendStats.error;
}

// افزودن به لاگ
function addToLog(message) {
    const logContainer = document.getElementById('logContainer');
    const timestamp = new Date().toLocaleTimeString('fa-IR');
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.textContent = `[${timestamp}] ${message}`;
    
    logContainer.appendChild(logEntry);
    logContainer.scrollTop = logContainer.scrollHeight;
}