const FORM_ID = 'f34eea78-272d-47fd-b944-487e79bb9941';

// Check server lock state
async function checkServerLock() {
    try {
        console.log('Fetching lock state for', FORM_ID);
        const resp = await fetch(`/api/debug/check-lock/${FORM_ID}`);
        console.log('Response status:', resp.status);
        if (!resp.ok) {
            throw new Error('HTTP ' + resp.status);
        }
        const data = await resp.json();
        console.log('Lock data:', data);
        const status = document.getElementById('server-status');
        status.innerHTML = `
            <strong>Status: ${data.status}</strong><br>
            <span class="${data.isLocked ? 'locked' : 'unlocked'}">
                ${data.isLocked ? '🔒 LOCKED' : '🔓 UNLOCKED'}
            </span><br>
            Locked At: ${data.lockedAt || 'N/A'}<br>
            Resources: ${data.resources}
        `;
    } catch (e) {
        console.error('Error:', e);
        document.getElementById('server-status').textContent = 'Error: ' + e.message + ' (check console)';
    }
}

// Check frontend (from form page)
async function checkFormLock() {
    try {
        const resp = await fetch(`/api/debug/last-lock-report`);
        const data = await resp.json();
        document.getElementById('lock-details').textContent = JSON.stringify(data, null, 2);
    } catch (e) {
        document.getElementById('lock-details').textContent = 'No report yet. Open form first.';
    }
}

// Run on page load
document.addEventListener('DOMContentLoaded', checkServerLock);
