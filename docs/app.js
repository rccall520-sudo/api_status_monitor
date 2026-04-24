function parseTime(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function getEntryTime(entry) {
    return entry.last_check || entry.timestamp || '';
}

function normalizeEntry(entry) {
    const source = entry && typeof entry === 'object' ? entry : {};
    const lastCheck = getEntryTime(source);
    const latency = Number.isFinite(source.latency_ms) ? source.latency_ms : null;

    return {
        timestamp: source.timestamp || lastCheck || '',
        last_check: lastCheck || '',
        api_base: source.api_base || '-',
        model: source.model || '-',
        http_status: source.http_status ?? null,
        latency_ms: latency,
        success: Boolean(source.success),
        token_output: Boolean(source.token_output),
        error_message: source.error_message || '',
    };
}

function normalizeHistory(history) {
    if (!Array.isArray(history)) return [];

    return history
        .map(normalizeEntry)
        .filter(entry => parseTime(getEntryTime(entry)))
        .sort((left, right) => parseTime(getEntryTime(left)) - parseTime(getEntryTime(right)));
}

async function loadData() {
    try {
        const cacheBuster = '?t=' + Date.now();
        const [statusRes, historyRes] = await Promise.all([
            fetch('data/status.json' + cacheBuster),
            fetch('data/history.json' + cacheBuster),
        ]);

        const status = normalizeEntry(await statusRes.json());
        const history = normalizeHistory(await historyRes.json());

        updateStatus(status);
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
    const errorBox = document.getElementById('error-box');
    const errorMessage = document.getElementById('error-message');

    if (data.success) {
        dot.className = 'status-indicator online';
        text.textContent = 'API 运行正常';
    } else {
        dot.className = 'status-indicator offline';
        text.textContent = 'API 不可用';
    }

    document.getElementById('api-base').textContent = data.api_base || '-';
    document.getElementById('model').textContent = data.model || '-';
    document.getElementById('http-status').textContent = data.http_status ?? '-';
    document.getElementById('latency').textContent = data.latency_ms !== null ? data.latency_ms + 'ms' : '-';
    document.getElementById('last-check').textContent = formatTime(getEntryTime(data));

    if (data.error_message) {
        errorBox.style.display = 'block';
        errorMessage.textContent = data.error_message;
    } else {
        errorBox.style.display = 'none';
        errorMessage.textContent = '';
    }
}

function updateStats(history) {
    const total = history.length;
    const success = history.filter(entry => entry.success).length;
    const uptime = total > 0 ? (success / total * 100).toFixed(1) : '0.0';

    const latencies = history
        .map(entry => entry.latency_ms)
        .filter(latency => Number.isFinite(latency));
    const avgLatency = latencies.length > 0
        ? Math.round(latencies.reduce((sum, latency) => sum + latency, 0) / latencies.length)
        : null;

    document.getElementById('uptime-percent').textContent = uptime + '%';
    document.getElementById('total-checks').textContent = total;
    document.getElementById('avg-latency').textContent = avgLatency !== null ? avgLatency + 'ms' : '-';
}

function bjHourKey(date) {
    const bj = new Date(date.getTime() + 8 * 3600000);
    const y = bj.getUTCFullYear();
    const m = String(bj.getUTCMonth() + 1).padStart(2, '0');
    const d = String(bj.getUTCDate()).padStart(2, '0');
    const h = String(bj.getUTCHours()).padStart(2, '0');
    return `${y}-${m}-${d}T${h}`;
}

function updateGrid(history) {
    const grid = document.getElementById('uptime-grid');
    grid.innerHTML = '';

    const hourly = {};
    const now = new Date();
    for (let i = 23; i >= 0; i -= 1) {
        const hour = new Date(now.getTime() - i * 3600000);
        hourly[bjHourKey(hour)] = null;
    }

    history.forEach(entry => {
        const date = parseTime(getEntryTime(entry));
        if (!date) return;

        const key = bjHourKey(date);
        if (!(key in hourly)) return;

        if (hourly[key] === null) {
            hourly[key] = entry.success;
        } else if (hourly[key] !== entry.success) {
            hourly[key] = 'partial';
        }
    });

    Object.values(hourly).forEach(value => {
        const cell = document.createElement('div');
        const stateClass = value === true ? 'success' : value === false ? 'fail' : '';
        cell.className = 'cell ' + stateClass;
        cell.title = value === true ? '正常' : value === false ? '异常' : value === 'partial' ? '部分异常' : '无数据';
        grid.appendChild(cell);
    });
}

function updateHistoryList(history) {
    const list = document.getElementById('history-list');
    list.innerHTML = '';

    history.slice(-20).reverse().forEach(entry => {
        const item = document.createElement('div');
        item.className = 'history-item';

        const icon = document.createElement('span');
        icon.className = 'history-icon ' + (entry.success ? 'success' : 'fail');

        const info = document.createElement('div');
        info.className = 'history-info';

        const timeNode = document.createElement('div');
        timeNode.className = 'history-time';
        timeNode.textContent = formatTime(getEntryTime(entry));

        const statusNode = document.createElement('div');
        statusNode.className = 'history-status';
        statusNode.textContent = entry.success ? '正常响应' : (entry.error_message || '请求失败');

        info.appendChild(timeNode);
        info.appendChild(statusNode);

        const latency = document.createElement('span');
        latency.className = 'history-latency';
        latency.textContent = entry.latency_ms !== null ? entry.latency_ms + 'ms' : '-';

        item.appendChild(icon);
        item.appendChild(info);
        item.appendChild(latency);
        list.appendChild(item);
    });
}

function formatTime(iso) {
    const date = parseTime(iso);
    if (!date) return '-';

    return date.toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    });
}

function showError(msg) {
    const errorBox = document.getElementById('error-box');
    document.getElementById('status-text').textContent = msg;
    document.getElementById('status-dot').className = 'status-indicator offline';
    errorBox.style.display = 'block';
    document.getElementById('error-message').textContent = msg;
}

loadData();
setInterval(loadData, 300000);
