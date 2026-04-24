function parseTime(value) {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

function formatTime(value) {
    const date = parseTime(value);
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

function getEntryTime(entry) {
    return entry.last_check || entry.timestamp || '';
}

function getTargetId(entry) {
    return entry.target_id || `${entry.target_name || entry.api_base || 'unknown'}::${entry.model || 'unknown'}`;
}

function normalizeEntry(entry) {
    const source = entry && typeof entry === 'object' ? entry : {};
    const lastCheck = getEntryTime(source);
    const latency = Number.isFinite(source.latency_ms) ? source.latency_ms : null;
    const hasIdentity = Boolean(source.target_name || source.name || source.api_base || source.model);

    return {
        target_id: source.target_id || '',
        target_name: hasIdentity ? (source.target_name || source.name || `${source.api_base || '-'} · ${source.model || '-'}`) : '',
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

function normalizeStatusPayload(raw) {
    if (raw && typeof raw === 'object' && Array.isArray(raw.targets)) {
        const targets = raw.targets.map(normalizeEntry);
        return {
            updated_at: raw.updated_at || '',
            summary: raw.summary || {},
            targets,
        };
    }

    const single = normalizeEntry(raw);
    return {
        updated_at: getEntryTime(single),
        summary: {
            target_count: single.target_name ? 1 : 0,
            online_count: single.success ? 1 : 0,
            offline_count: single.success ? 0 : 1,
        },
        targets: single.target_name ? [single] : [],
    };
}

function normalizeHistoryPayload(raw) {
    const entries = Array.isArray(raw)
        ? raw
        : raw && typeof raw === 'object' && Array.isArray(raw.entries)
            ? raw.entries
            : [];

    return entries
        .map(normalizeEntry)
        .filter(entry => parseTime(getEntryTime(entry)))
        .sort((left, right) => parseTime(getEntryTime(left)) - parseTime(getEntryTime(right)));
}

function calculateStats(history) {
    const totalChecks = history.length;
    const successChecks = history.filter(entry => entry.success).length;
    const latencies = history
        .map(entry => entry.latency_ms)
        .filter(latency => Number.isFinite(latency));

    return {
        totalChecks,
        successChecks,
        avgLatency: latencies.length
            ? Math.round(latencies.reduce((sum, latency) => sum + latency, 0) / latencies.length)
            : null,
    };
}

function bjHourKey(date) {
    const bj = new Date(date.getTime() + 8 * 3600000);
    const y = bj.getUTCFullYear();
    const m = String(bj.getUTCMonth() + 1).padStart(2, '0');
    const d = String(bj.getUTCDate()).padStart(2, '0');
    const h = String(bj.getUTCHours()).padStart(2, '0');
    return `${y}-${m}-${d}T${h}`;
}

function buildHourlyMap(entries) {
    const hourly = {};
    const now = new Date();
    for (let i = 23; i >= 0; i -= 1) {
        const hour = new Date(now.getTime() - i * 3600000);
        hourly[bjHourKey(hour)] = null;
    }

    entries.forEach(entry => {
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

    return hourly;
}

function renderEmpty(container, text) {
    container.innerHTML = '';
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = text;
    container.appendChild(empty);
}

function updateSummary(statusPayload, history) {
    const stats = calculateStats(history);
    const targetCount = statusPayload.targets.length;
    const onlineCount = statusPayload.targets.filter(target => target.success).length;

    document.getElementById('page-updated').textContent = formatTime(statusPayload.updated_at);
    document.getElementById('target-total').textContent = targetCount;
    document.getElementById('target-online').textContent = `${onlineCount}/${targetCount || 0}`;
    document.getElementById('total-checks').textContent = stats.totalChecks;
    document.getElementById('avg-latency').textContent = stats.avgLatency !== null ? `${stats.avgLatency}ms` : '-';
}

function updateTargetCards(statusPayload, history) {
    const container = document.getElementById('targets-grid');
    container.innerHTML = '';

    if (!statusPayload.targets.length) {
        renderEmpty(container, '还没有可展示的监控目标。');
        return;
    }

    const historyByTarget = new Map();
    history.forEach(entry => {
        const key = getTargetId(entry);
        if (!historyByTarget.has(key)) {
            historyByTarget.set(key, []);
        }
        historyByTarget.get(key).push(entry);
    });

    statusPayload.targets.forEach(target => {
        const key = getTargetId(target);
        const targetHistory = historyByTarget.get(key) || [];
        const successChecks = targetHistory.filter(entry => entry.success).length;
        const uptime = targetHistory.length ? ((successChecks / targetHistory.length) * 100).toFixed(1) : '0.0';

        const card = document.createElement('article');
        card.className = 'target-card';

        const header = document.createElement('div');
        header.className = 'target-card-header';

        const titleWrap = document.createElement('div');
        titleWrap.className = 'target-title-wrap';

        const dot = document.createElement('span');
        dot.className = `status-indicator ${target.success ? 'online' : 'offline'}`;

        const titleBox = document.createElement('div');

        const name = document.createElement('div');
        name.className = 'target-name';
        name.textContent = target.target_name;

        const subtitle = document.createElement('div');
        subtitle.className = 'target-subtitle';
        subtitle.textContent = `${target.api_base} · ${target.model}`;

        titleBox.appendChild(name);
        titleBox.appendChild(subtitle);
        titleWrap.appendChild(dot);
        titleWrap.appendChild(titleBox);

        const badge = document.createElement('span');
        badge.className = `status-badge ${target.success ? 'online' : 'offline'}`;
        badge.textContent = target.success ? 'ONLINE' : 'OFFLINE';

        header.appendChild(titleWrap);
        header.appendChild(badge);

        const details = document.createElement('div');
        details.className = 'target-details';
        details.appendChild(createDetailRow('HTTP状态', target.http_status ?? '-'));
        details.appendChild(createDetailRow('响应延迟', target.latency_ms !== null ? `${target.latency_ms}ms` : '-'));
        details.appendChild(createDetailRow('最后检测', formatTime(getEntryTime(target))));
        details.appendChild(createDetailRow('7天可用率', `${uptime}%`));

        card.appendChild(header);
        card.appendChild(details);

        if (target.error_message) {
            const errorBox = document.createElement('div');
            errorBox.className = 'error-box';
            errorBox.textContent = target.error_message;
            card.appendChild(errorBox);
        }

        container.appendChild(card);
    });
}

function createDetailRow(labelText, valueText) {
    const row = document.createElement('div');
    row.className = 'detail-row';

    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = labelText;

    const value = document.createElement('span');
    value.className = 'value';
    value.textContent = valueText;

    row.appendChild(label);
    row.appendChild(value);
    return row;
}

function updateTargetGrids(statusPayload, history) {
    const container = document.getElementById('target-grids');
    container.innerHTML = '';

    if (!statusPayload.targets.length) {
        renderEmpty(container, '暂无最近24小时数据。');
        return;
    }

    const historyByTarget = new Map();
    history.forEach(entry => {
        const key = getTargetId(entry);
        if (!historyByTarget.has(key)) {
            historyByTarget.set(key, []);
        }
        historyByTarget.get(key).push(entry);
    });

    statusPayload.targets.forEach(target => {
        const key = getTargetId(target);
        const targetHistory = historyByTarget.get(key) || [];
        const hourly = buildHourlyMap(targetHistory);

        const row = document.createElement('div');
        row.className = 'grid-row';

        const meta = document.createElement('div');
        meta.className = 'grid-meta';

        const title = document.createElement('div');
        title.className = 'grid-title';
        title.textContent = target.target_name;

        const caption = document.createElement('div');
        caption.className = 'grid-caption';
        caption.textContent = `${target.api_base} · ${target.model}`;

        meta.appendChild(title);
        meta.appendChild(caption);

        const grid = document.createElement('div');
        grid.className = 'uptime-grid';

        Object.values(hourly).forEach(value => {
            const cell = document.createElement('div');
            let stateClass = '';
            if (value === true) stateClass = 'success';
            if (value === false) stateClass = 'fail';
            if (value === 'partial') stateClass = 'partial';

            cell.className = `cell ${stateClass}`.trim();
            cell.title = value === true ? '正常' : value === false ? '异常' : value === 'partial' ? '混合' : '无数据';
            grid.appendChild(cell);
        });

        row.appendChild(meta);
        row.appendChild(grid);
        container.appendChild(row);
    });
}

function updateHistoryList(history) {
    const container = document.getElementById('history-list');
    container.innerHTML = '';

    if (!history.length) {
        renderEmpty(container, '暂无检测记录。');
        return;
    }

    history.slice(-30).reverse().forEach(entry => {
        const item = document.createElement('div');
        item.className = 'history-item';

        const icon = document.createElement('span');
        icon.className = `history-icon ${entry.success ? 'success' : 'fail'}`;

        const targetBox = document.createElement('div');
        targetBox.className = 'history-target';

        const targetName = document.createElement('div');
        targetName.className = 'history-name';
        targetName.textContent = entry.target_name;

        const targetModel = document.createElement('div');
        targetModel.className = 'history-model';
        targetModel.textContent = `${entry.api_base} · ${entry.model}`;

        targetBox.appendChild(targetName);
        targetBox.appendChild(targetModel);

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
        latency.textContent = entry.latency_ms !== null ? `${entry.latency_ms}ms` : '-';

        item.appendChild(icon);
        item.appendChild(targetBox);
        item.appendChild(info);
        item.appendChild(latency);
        container.appendChild(item);
    });
}

function showError(message) {
    document.getElementById('page-updated').textContent = '加载失败';
    renderEmpty(document.getElementById('targets-grid'), message);
    renderEmpty(document.getElementById('target-grids'), message);
    renderEmpty(document.getElementById('history-list'), message);
}

async function loadData() {
    try {
        const cacheBuster = `?t=${Date.now()}`;
        const [statusRes, historyRes] = await Promise.all([
            fetch(`data/status.json${cacheBuster}`),
            fetch(`data/history.json${cacheBuster}`),
        ]);

        const statusPayload = normalizeStatusPayload(await statusRes.json());
        const history = normalizeHistoryPayload(await historyRes.json());

        updateSummary(statusPayload, history);
        updateTargetCards(statusPayload, history);
        updateTargetGrids(statusPayload, history);
        updateHistoryList(history);
    } catch (error) {
        showError(`无法加载数据: ${error.message}`);
    }
}

loadData();
setInterval(loadData, 300000);
