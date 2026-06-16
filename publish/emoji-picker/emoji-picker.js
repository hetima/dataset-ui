/**
 * EmojiPicker — textarea に絵文字コンボボックスを取り付けるバニラ JS モジュール。
 * `:keyword` でトリガー。上下キーで選択、Enter で確定、Escape で閉じる。
 */
window.EmojiPicker = (() => {
  const MAX_ITEMS = 20;

  /**
   * @param {HTMLTextAreaElement} ta
   * @param {Array<{emoji:string, labelJa:string, keywords:string[]}>} emojiData
   */
  function attach(ta, emojiData) {
    if (ta.__emojiPickerAttached) return;
    ta.__emojiPickerAttached = true;

    // ドロップダウン要素を作る
    const dropdown = document.createElement('div');
    Object.assign(dropdown.style, {
      position: 'absolute',
      zIndex: '9999',
      background: '#fff',
      border: '1px solid #ccc',
      borderRadius: '6px',
      boxShadow: '0 4px 12px rgba(0,0,0,.15)',
      maxHeight: '260px',
      overflowY: 'auto',
      display: 'none',
      minWidth: '220px',
    });
    // textarea の親に relative + dropdown を追加
    const wrapper = ta.closest('.q-field') || ta.parentElement;
    wrapper.style.position = 'relative';
    wrapper.appendChild(dropdown);

    let activeIndex = -1;
    let items = [];

    // カーソル位置より前のテキストから `:query` / `：query` を探す
    function getTrigger() {
      const val = ta.value;
      const pos = ta.selectionStart;
      const before = val.slice(0, pos);
      // 直近の `:` または `：` を探す（スペース・改行を超えない）
      const m = before.match(/[:：]([^\s:：]*)$/);
      if (!m) return null;
      return { query: m[1], colonIndex: pos - m[0].length };
    }

    function filter(query) {
      const q = query.toLowerCase();
      return emojiData
        .filter(e => e.keywords.some(k => k.toLowerCase().startsWith(q)))
        .slice(0, MAX_ITEMS);
    }

    function renderItems() {
      dropdown.innerHTML = '';
      items.forEach((e, i) => {
        const row = document.createElement('div');
        Object.assign(row.style, {
          padding: '6px 12px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '14px',
          background: i === activeIndex ? '#e8f0fe' : '',
        });
        const emoji = document.createElement('span');
        emoji.style.fontSize = '20px';
        emoji.textContent = e.emoji;
        const label = document.createElement('span');
        label.textContent = e.labelJa;
        row.append(emoji, label);
        row.addEventListener('mousedown', ev => {
          ev.preventDefault();
          select(i);
        });
        row.addEventListener('mousemove', () => {
          activeIndex = i;
          renderItems();
        });
        dropdown.appendChild(row);
      });
    }

    function open(filtered) {
      items = filtered;
      activeIndex = 0;
      renderItems();
      dropdown.style.display = 'block';
      // textarea の下端に合わせる
      dropdown.style.top = (ta.offsetTop + ta.offsetHeight) + 'px';
      dropdown.style.left = ta.offsetLeft + 'px';
    }

    function close() {
      dropdown.style.display = 'none';
      items = [];
      activeIndex = -1;
    }

    function select(index) {
      const trigger = getTrigger();
      if (!trigger || !items[index]) { close(); return; }
      const emoji = items[index].emoji;
      const val = ta.value;
      const pos = ta.selectionStart;
      const before = val.slice(0, trigger.colonIndex);
      const after = val.slice(pos);
      const newVal = before + emoji + after;
      // NiceGUI の v-model を更新するために native input event を発火
      const nativeInput = ta;
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
      setter.set.call(nativeInput, newVal);
      nativeInput.dispatchEvent(new Event('input', { bubbles: true }));
      // カーソルを絵文字の直後に移動
      const newPos = trigger.colonIndex + emoji.length;
      nativeInput.setSelectionRange(newPos, newPos);
      close();
    }

    ta.addEventListener('input', () => {
      const trigger = getTrigger();
      if (!trigger) { close(); return; }
      const filtered = filter(trigger.query);
      if (!filtered.length) { close(); return; }
      open(filtered);
    });

    ta.addEventListener('keydown', ev => {
      if (dropdown.style.display === 'none') return;
      if (ev.key === 'ArrowDown') {
        ev.preventDefault();
        activeIndex = Math.min(activeIndex + 1, items.length - 1);
        renderItems();
        // スクロール追従
        const rows = dropdown.querySelectorAll('div');
        rows[activeIndex]?.scrollIntoView({ block: 'nearest' });
      } else if (ev.key === 'ArrowUp') {
        ev.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        renderItems();
        const rows = dropdown.querySelectorAll('div');
        rows[activeIndex]?.scrollIntoView({ block: 'nearest' });
      } else if (ev.key === 'Enter') {
        if (activeIndex >= 0) {
          ev.preventDefault();
          select(activeIndex);
        }
      } else if (ev.key === 'Escape') {
        close();
      }
    });

    ta.addEventListener('blur', () => {
      // mousedown で select する前に blur が来るので少し遅延
      setTimeout(close, 150);
    });
  }

  return { attach };
})();
