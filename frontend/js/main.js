// frontend/js/main.js
const API_BASE_URL = 'http://localhost:5000/api';

// مدیریت تب‌ها
let currentTab = 'dashboardTab';

function showTab(tabId) {
    // مخفی کردن همه تب‌ها
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // نمایش تب انتخاب شده
    const selectedTab = document.getElementById(tabId);
    if (selectedTab) {
        selectedTab.classList.add('active');
        currentTab = tabId;
        
        // بارگذاری داده‌های تب
        loadTabData(tabId);
    }
}

function loadTabData(tabId) {
    switch(tabId) {
        case 'dashboardTab':
            loadDashboard();
            break;
        case 'loginTab':
            checkLoginStatus();
            break;
        case 'contactsTab':
            loadContacts();
            break;
        case 'sendTab':
            loadSendTab();
            break;
        case 'settingsTab':
            loadSettings();
            break;
        case 'reportsTab':
            loadReports();
            break;
    }
}

// بارگذاری داشبورد
async function loadDashboard() {
    try {
        const response = await fetch(`${API_BASE_URL}/reports`);
        const data = await response.json();
        
        // محاسبه آمار
        let total = 0, success = 0, error = 0;
        data.forEach(report => {
            total += report.total;
            success += report.success;
            error += report.errors;
        });
        
        document.getElementById('totalMessages').textContent = total.toLocaleString();
        document.getElementById('successMessages').textContent = success.toLocaleString();
        document.getElementById('errorMessages').textContent = error.toLocaleString();
        
        if (total > 0) {
            const avgTime = (total * 3.5 / 60).toFixed(1);
            document.getElementById('avgTime').textContent = `${avgTime} دقیقه`;
        }
        
        // آپدیت وضعیت
        updateStatusBar();
    } catch (error) {
        console.error('خطا در بارگذاری داشبورد:', error);
    }
}

// بررسی وضعیت لاگین
async function checkLoginStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/login/status`);
        const data = await response.json();
        
        const statusElement = document.getElementById('sessionStatus');
        const loginBtn = document.getElementById('loginBtn');
        const confirmBtn = document.getElementById('confirmBtn');
        const logoutBtn = document.getElementById('logoutBtn');
        
        if (data.logged_in) {
            statusElement.innerHTML = '<i class="fas fa-check-circle text-success"></i> <span>وارد شده‌اید</span>';
            loginBtn.disabled = true;
            confirmBtn.disabled = true;
            logoutBtn.disabled = false;
            
            // آپدیت هدر
            document.getElementById('loginStatus').innerHTML = 
                '<i class="fas fa-user-check"></i> <span>وارد شده</span>';
        } else {
            statusElement.innerHTML = '<i class="fas fa-times-circle text-danger"></i> <span>وارد نشده‌اید</span>';
            loginBtn.disabled = false;
            confirmBtn.disabled = false;
            logoutBtn.disabled = true;
        }
    } catch (error) {
        console.error('خطا در بررسی وضعیت لاگین:', error);
    }
}

// شروع لاگین
function startLogin() {
    // در نسخه واقعی اینجا مرورگر باز می‌شود
    alert('در نسخه دمو، این بخش شبیه‌سازی شده است. در نسخه واقعی مرورگر برای لاگین باز می‌شود.');
    
    // شبیه‌سازی لاگین موفق
    setTimeout(() => {
        document.getElementById('confirmBtn').disabled = false;
        showNotification('لاگین موفقیت‌آمیز بود!', 'success');
    }, 2000);
}

// تأیید لاگین
function confirmLogin() {
    // در اینجا با سرور ارتباط برقرار می‌شود تا وضعیت لاگین تأیید شود
    showNotification('لاگین تأیید شد!', 'success');
    checkLoginStatus();
}

// خروج
function logout() {
    if (confirm('آیا می‌خواهید از حساب ایتا خارج شوید؟')) {
        // حذف نشست
        fetch(`${API_BASE_URL}/login/logout`, { method: 'POST' })
            .then(() => {
                showNotification('با موفقیت خارج شدید', 'info');
                checkLoginStatus();
            })
            .catch(error => {
                showNotification('خطا در خروج', 'error');
            });
    }
}

// بارگذاری مخاطبان
async function loadContacts() {
    try {
        const response = await fetch(`${API_BASE_URL}/contacts`);
        const contacts = await response.json();
        
        const tbody = document.getElementById('contactsTable');
        const totalElement = document.getElementById('contactsTotal');
        const statusCount = document.getElementById('contactsCount');
        
        tbody.innerHTML = '';
        totalElement.textContent = contacts.length;
        statusCount.textContent = contacts.length;
        
        contacts.forEach((contact, index) => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><input type="checkbox" class="contact-checkbox" value="${contact.id}"></td>
                <td>${index + 1}</td>
                <td>${contact.user_id}</td>
                <td><span class="badge">${contact.source}</span></td>
                <td>${new Date(contact.added_date).toLocaleDateString('fa-IR')}</td>
                <td>
                    <button class="btn btn-danger btn-sm" onclick="deleteContact(${contact.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            `;
            tbody.appendChild(row);
        });
        
        // مدیریت انتخاب همه
        document.getElementById('selectAll').addEventListener('change', function() {
            document.querySelectorAll('.contact-checkbox').forEach(checkbox => {
                checkbox.checked = this.checked;
            });
        });
    } catch (error) {
        console.error('خطا در بارگذاری مخاطبان:', error);
    }
}

// مدیریت آپلود فایل
document.getElementById('fileInput').addEventListener('change', async function(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_BASE_URL}/contacts/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showNotification(result.message, 'success');
            loadContacts();
        } else {
            showNotification(result.error, 'error');
        }
    } catch (error) {
        showNotification('خطا در آپلود فایل', 'error');
    }
});

// درگ و دراپ
const dropZone = document.getElementById('dropZone');
dropZone.addEventListener('dragover', function(e) {
    e.preventDefault();
    this.style.borderColor = 'var(--primary-color)';
    this.style.backgroundColor = 'rgba(74, 111, 165, 0.1)';
});

dropZone.addEventListener('dragleave', function() {
    this.style.borderColor = '#ddd';
    this.style.backgroundColor = '';
});

dropZone.addEventListener('drop', function(e) {
    e.preventDefault();
    this.style.borderColor = '#ddd';
    this.style.backgroundColor = '';
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        document.getElementById('fileInput').files = files;
        document.getElementById('fileInput').dispatchEvent(new Event('change'));
    }
});

// حذف مخاطب
function deleteContact(id) {
    if (confirm('آیا می‌خواهید این مخاطب را حذف کنید؟')) {
        fetch(`${API_BASE_URL}/contacts`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: [id] })
        })
        .then(() => {
            showNotification('مخاطب حذف شد', 'success');
            loadContacts();
        })
        .catch(error => {
            showNotification('خطا در حذف مخاطب', 'error');
        });
    }
}

// حذف مخاطبان انتخاب شده
function deleteSelectedContacts() {
    const checkboxes = document.querySelectorAll('.contact-checkbox:checked');
    const ids = Array.from(checkboxes).map(cb => parseInt(cb.value));
    
    if (ids.length === 0) {
        showNotification('هیچ مخاطبی انتخاب نشده است', 'warning');
        return;
    }
    
    if (confirm(`آیا می‌خواهید ${ids.length} مخاطب را حذف کنید؟`)) {
        fetch(`${API_BASE_URL}/contacts`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids })
        })
        .then(() => {
            showNotification(`${ids.length} مخاطب حذف شدند`, 'success');
            loadContacts();
        })
        .catch(error => {
            showNotification('خطا در حذف مخاطبان', 'error');
        });
    }
}

// بروزرسانی نوار وضعیت
function updateStatusBar() {
    fetch(`${API_BASE_URL}/bot/status`)
        .then(response => response.json())
        .then(data => {
            document.getElementById('botStatusText').textContent = data.current_action;
        })
        .catch(console.error);
}

// نمایش نوتیفیکیشن
function showNotification(message, type = 'info') {
    // ایجاد عنصر نوتیفیکیشن
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()">×</button>
    `;
    
    // استایل‌های نوتیفیکیشن
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 20px;
        right: 20px;
        background: ${type === 'success' ? '#28a745' : type === 'error' ? '#dc3545' : '#17a2b8'};
        color: white;
        padding: 15px;
        border-radius: var(--border-radius);
        display: flex;
        justify-content: space-between;
        align-items: center;
        z-index: 9999;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    // حذف خودکار پس از 5 ثانیه
    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 5000);
}

// اضافه کردن استایل انیمیشن
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateY(-100%); opacity: 0; }
        to { transform: translateY(0); opacity: 1; }
    }
    
    .badge {
        background: #e9ecef;
        color: #495057;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.85rem;
    }
`;
document.head.appendChild(style);

// بارگذاری اولیه
document.addEventListener('DOMContentLoaded', function() {
    // نمایش تب داشبورد
    showTab('dashboardTab');
    
    // شروع بروزرسانی وضعیت
    setInterval(updateStatusBar, 5000);
    
    // بارگذاری اولیه مخاطبان
    loadContacts();
});