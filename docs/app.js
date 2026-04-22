async function loadData() {
    try {
        const statusRes = await fetch('data/status.json?t=' + Date.now());
        const status = await statusRes.json();
        updateStatus(status);

        const historyRes = await fetch('data/history.json?t=' + Date.now());
        const history = await historyRes.json();
        updateStats(history);
        updateGrid(history);
        updateHistoryList(history);
    } catch (e) {
        showError('无法加载数据: ' + e.message);
    }
}

function updateStatus(data) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    if (data.success) {
        dot.className = 'status-indicator online';
        text.textContent = 'API 运行正常';
    } else {
        dot.className = 'status-indicator offline';
        text.textContent = 'API 不可用';
    }

    document.getElementById('api-base').textContent = data.api_base || '-';
    document.getElementById('model').textContent = data.model || '-';
    document.getElementById('http-status').textContent = data.http_status || '-';
    document.getElementById('latency').textContent = data.latency_ms ? data.latency_ms + 'ms' : '-';
    document.getElementById('last-check').textContent = formatTime(data.last_check);

    if (data.error_message) {
        document.getElementById('error-box').style.display = 'block';
        document.getElementById('error-message').textContent = data.error_message;
    }
}

function updateStats(history) {
    if (!history || !Array.isArray(history)) return;

    const total = history.length;
    const success = history.filter(h => h.success).length;
    const uptime = total > 0 ? (success / total * 100).toFixed(1) : 0;

    const latencies = history.filter(h => h.latency_ms).map(h => h.latency_ms);
    const avgLatency = latencies.length > 0
        ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length)
        : 0;

    document.getElementById('uptime-percent').textContent = uptime + '%';
    document.getElementById('total-checks').textContent = total;
    document.getElementById('avg-latency').textContent = avgLatency + 'ms';
}

// 按北京时间取整点 key，如 "2026-04-23T14"
function bjHourKey(date) {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', hour12: false
    }).formatToParts(date);
    const get = type => parts.find(p => p.type === type)?.value || '';
    return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}`;
}

function updateGrid(history) {
    const grid = document.getElementById('uptime-grid');
    grid.innerHTML = '';

    if (!history || !Array.isArray(history)) return;

    // 生成最近24个北京时间的整点槽位
    const hourly = {};
    const now = new Date();
    for (let i = 23; i >= 0; i--) {
        const hour = new Date(now.getTime() - i * 3600000);
        hourly[bjHourKey(hour)] = null;
    }

    // 填充数据
    history.forEach(h => {
        const ts = h.timestamp || h.last_check;
        if (!ts) return;
        const key = bjHourKey(new Date(ts));
        if (key in hourly) {
            if (hourly[key] === null) {
                hourly[key] = h.success;
            } else if (hourly[key] !== h.success) {
                hourly[key] = 'partial';
            }
        }
    });

    Object.values(hourly).forEach(val => {
        const cell = document.createElement('div');
        cell.className = 'cell ' + (val === true ? 'success' : val === false ? 'fail' : '');
        cell.title = val === true ? '正常' : val === false ? '异常' : '无数据';
        grid.appendChild(cell);
    });
}

function updateHistoryList(history) {
    const list = document.getElementById('history-list');
    list.innerHTML = '';

    if (!history || !Array.isArray(history)) return;

    const recent = history.slice(-20).reverse();

    recent.forEach(h => {
        const item = document.createElement('div');
        item.className = 'history-item';

        const icon = document.createElement('span');
        icon.className = 'history-icon ' + (h.success ? 'success' : 'fail');

        const info = document.createElement('div');
        info.className = 'history-info';

        const ts = h.timestamp || h.last_check;
        const error = h.error_message || '';

        info.innerHTML = `
            <div class="history-time">${formatTime(ts)}</div>
            <div class="history-status">${h.success ? '正常响应' : (error || '请求失败')}</div>
        `;

        const latency = document.createElement('span');
        latency.className = 'history-latency';
        latency.textContent = h.latency_ms ? h.latency_ms + 'ms' : '-';

        item.appendChild(icon);
        item.appendChild(info);
        item.appendChild(latency);
        list.appendChild(item);
    });
}

function formatTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function showError(msg) {
    document.getElementById('status-text').textContent = msg;
    document.getElementById('status-dot').className = 'status-indicator offline';
}

loadData();
setInterval(loadData, 300000);
