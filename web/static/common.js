/**
 * AI Video - 共享前端逻辑
 */
(function () {
  'use strict';

  window.AIVideo = {
    log: function (container, msg, options) {
      const line = document.createElement('div');
      line.className = 'log-line' + (options?.waiting ? ' waiting' : '') + (options?.error ? ' error' : '');
      line.textContent = msg;
      container.appendChild(line);
      container.scrollTop = container.scrollHeight;
    },

    showSkipBtns: function (el, show) {
      el.classList.toggle('hidden', !show);
    },

    setStatus: function (wrap, text, cls) {
      wrap.innerHTML = cls ? '<span class="status ' + cls + '">' + text + '</span>' : '';
    },

    isWaitingLog: function (text) {
      return /等待|OpenClaw|发送给/.test(text || '');
    },

    skipOpenClaw: async function (apiPath, mode, logContainer, logFn) {
      let url = apiPath;
      if (mode === 'file') {
        const fn = prompt('输入文件名（如 xxx.mp4）：');
        if (fn == null) return;
        url += '?filename=' + encodeURIComponent(fn);
      }
      try {
        await fetch(url, { method: 'POST' });
        logFn('✓ ' + (mode === 'file' ? '已选择指定文件继续' : '已选择使用最新视频继续'));
      } catch (e) {
        logFn('跳过失败: ' + e.message, { error: true });
      }
    }
  };
})();
