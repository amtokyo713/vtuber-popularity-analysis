"""HTMLレポートをAES-256-GCMで暗号化し、パスワード保護されたindex.htmlを生成する.

- output/report.html を読み込む
- PBKDF2(SHA-256, 200000 iterations) でパスワードからキー導出
- AES-256-GCM で暗号化
- salt/nonce/ciphertext を Base64 化して JS の Web Crypto API で復号できる形式に
- ルートの index.html を「パスワード入力 → 復号 → 表示」する単一HTMLに置き換え
- output/report.html, output/preview.html もパスワード必要のリダイレクトに差し替え
  (これらに直接アクセスされても素通りされないようにする)

使い方:
  python src/encrypt_report.py [PASSWORD]
  PASSWORDを省略すると環境変数 REPORT_PASSWORD を使う
  どちらもなければ "vtuber2026" がデフォルト
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = PROJECT_ROOT / "output" / "report.html"
PREVIEW_PATH = PROJECT_ROOT / "output" / "preview.html"
INDEX_PATH = PROJECT_ROOT / "index.html"

PBKDF2_ITERATIONS = 200000


def encrypt_html(plaintext: bytes, password: str) -> dict[str, str]:
    salt = os.urandom(16)
    nonce = os.urandom(12)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(password.encode("utf-8"))

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    return {
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "iterations": PBKDF2_ITERATIONS,
    }


PROTECTED_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>新人VTuber 人気要因 総合分析レポート (パスワード保護)</title>
<style>
  :root {
    --bg: #0f1117;
    --panel: #191c26;
    --panel2: #232736;
    --text: #e8eaf6;
    --muted: #8a90a6;
    --accent: #ff4081;
    --accent2: #5e7bff;
    --line: #2a2e3d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: linear-gradient(135deg, #0f1117 0%, #1a1024 100%);
    color: var(--text);
    font-family: -apple-system, "Segoe UI", "Hiragino Kaku Gothic ProN", "Noto Sans JP", Meiryo, sans-serif;
    min-height: 100vh;
  }
  .gate {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .gate-card {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 36px 40px;
    max-width: 460px;
    width: 100%;
    box-shadow: 0 20px 50px rgba(0,0,0,0.5);
  }
  .gate-card h1 {
    margin: 0 0 6px;
    font-size: 22px;
    color: var(--accent);
  }
  .gate-card .sub {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 20px;
  }
  .gate-card label {
    display: block;
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 6px;
  }
  .gate-card input[type="password"] {
    width: 100%;
    padding: 12px 14px;
    background: var(--panel2);
    border: 1px solid var(--line);
    border-radius: 8px;
    color: var(--text);
    font-size: 16px;
    outline: none;
    margin-bottom: 12px;
  }
  .gate-card input[type="password"]:focus {
    border-color: var(--accent);
  }
  .gate-card button {
    width: 100%;
    padding: 12px 14px;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
  }
  .gate-card button:hover { opacity: 0.9; }
  .gate-card button:disabled { opacity: 0.5; cursor: wait; }
  .gate-card .status {
    margin-top: 14px;
    font-size: 13px;
    min-height: 1.2em;
  }
  .gate-card .status.error { color: #ff5252; }
  .gate-card .status.ok { color: #66bb6a; }
  .gate-card .note {
    margin-top: 18px;
    font-size: 11px;
    color: var(--muted);
    line-height: 1.6;
    border-top: 1px solid var(--line);
    padding-top: 14px;
  }
  .loading {
    display: none;
    text-align: center;
    padding: 40px;
    color: var(--muted);
    font-size: 14px;
  }
  .loading.show { display: block; }
  #report-frame {
    display: none;
    border: 0;
    width: 100vw;
    height: 100vh;
  }
</style>
</head>
<body>

<div class="gate" id="gate">
  <div class="gate-card">
    <h1>📊 新人VTuber 分析レポート</h1>
    <div class="sub">パスワードを入力すると閲覧できます</div>
    <form id="gate-form">
      <label for="pw">パスワード</label>
      <input type="password" id="pw" autocomplete="current-password" autofocus />
      <button type="submit" id="submit">レポートを開く 🔓</button>
    </form>
    <div class="status" id="status"></div>
    <div class="note">
      ※ このレポートはAES-256-GCMで暗号化されており、正しいパスワードでブラウザ復号されます。
      パスワード総当たりには時間がかかりますが、機密情報の保護を保証するものではありません。
    </div>
  </div>
</div>

<div class="loading" id="loading">復号中... しばらくお待ちください</div>
<iframe id="report-frame" sandbox="allow-scripts allow-popups allow-same-origin"></iframe>

<script id="payload" type="application/json">__PAYLOAD_JSON__</script>
<script>
const PAYLOAD = JSON.parse(document.getElementById('payload').textContent);

function b64ToBytes(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function deriveKey(password, salt, iterations) {
  const enc = new TextEncoder();
  const km = await crypto.subtle.importKey(
    'raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']
  );
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations, hash: 'SHA-256' },
    km,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt']
  );
}

async function tryDecrypt(password) {
  const salt = b64ToBytes(PAYLOAD.salt);
  const nonce = b64ToBytes(PAYLOAD.nonce);
  const ct = b64ToBytes(PAYLOAD.ciphertext);
  const key = await deriveKey(password, salt, PAYLOAD.iterations);
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: nonce },
    key,
    ct
  );
  return new TextDecoder('utf-8').decode(plain);
}

document.getElementById('gate-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const pw = document.getElementById('pw').value;
  const statusEl = document.getElementById('status');
  const submitBtn = document.getElementById('submit');
  const gate = document.getElementById('gate');
  const loading = document.getElementById('loading');
  const frame = document.getElementById('report-frame');

  if (!pw) {
    statusEl.textContent = 'パスワードを入力してください';
    statusEl.className = 'status error';
    return;
  }

  submitBtn.disabled = true;
  statusEl.textContent = '復号中...';
  statusEl.className = 'status';

  try {
    const html = await tryDecrypt(pw);
    statusEl.textContent = '✓ 復号成功 — レポートを読み込み中...';
    statusEl.className = 'status ok';

    // 復号成功 → iframe に書き込んで表示
    gate.style.display = 'none';
    loading.classList.add('show');

    // ブラウザの srcdoc で書き込み (大きいHTMLでも動作する)
    setTimeout(() => {
      frame.srcdoc = html;
      frame.style.display = 'block';
      loading.classList.remove('show');
      // セッションストレージに保存(同タブ内のリロードで再入力不要)
      try { sessionStorage.setItem('vtuber-report-pw', pw); } catch (e) {}
    }, 100);
  } catch (err) {
    statusEl.textContent = '✕ パスワードが違います';
    statusEl.className = 'status error';
    submitBtn.disabled = false;
    document.getElementById('pw').select();
  }
});

// セッションストレージから自動復元
window.addEventListener('DOMContentLoaded', () => {
  try {
    const saved = sessionStorage.getItem('vtuber-report-pw');
    if (saved) {
      document.getElementById('pw').value = saved;
      document.getElementById('gate-form').dispatchEvent(new Event('submit'));
    }
  } catch (e) {}
});
</script>
</body>
</html>
"""

REDIRECT_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>パスワードが必要です</title>
<meta http-equiv="refresh" content="2; url=../" />
<style>
  body {
    background: #0f1117;
    color: #e8eaf6;
    font-family: -apple-system, "Segoe UI", "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    margin: 0;
  }
  .box {
    text-align: center;
    padding: 40px;
    background: #191c26;
    border: 1px solid #2a2e3d;
    border-radius: 14px;
    max-width: 500px;
  }
  h1 { color: #ff4081; font-size: 22px; margin: 0 0 12px; }
  a { color: #80cbc4; text-decoration: none; font-size: 16px; }
  a:hover { text-decoration: underline; }
  p { color: #8a90a6; font-size: 13px; }
</style>
</head>
<body>
<div class="box">
  <h1>🔒 パスワードが必要です</h1>
  <p>このレポートはパスワード保護されています。</p>
  <p>2秒後にパスワード入力画面へ移動します...</p>
  <p><a href="../">→ 今すぐ移動</a></p>
</div>
</body>
</html>
"""


def main() -> None:
    password = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("REPORT_PASSWORD", "vtuber2026")
    )

    if not REPORT_PATH.exists():
        raise SystemExit(f"not found: {REPORT_PATH}. run main.py first.")

    print(f"[encrypt] reading {REPORT_PATH.relative_to(PROJECT_ROOT)} ...")
    plaintext = REPORT_PATH.read_bytes()
    print(f"[encrypt] plaintext size: {len(plaintext):,} bytes")

    print(f"[encrypt] encrypting with AES-256-GCM (PBKDF2 {PBKDF2_ITERATIONS:,} iter)...")
    payload = encrypt_html(plaintext, password)
    print(f"[encrypt] ciphertext size: {len(payload['ciphertext']):,} chars (base64)")

    payload_json = json.dumps(payload, ensure_ascii=False)
    html = PROTECTED_TEMPLATE.replace("__PAYLOAD_JSON__", payload_json)

    print(f"[encrypt] writing {INDEX_PATH.relative_to(PROJECT_ROOT)} ...")
    INDEX_PATH.write_text(html, encoding="utf-8")
    print(f"[encrypt] index.html size: {INDEX_PATH.stat().st_size:,} bytes")

    # output/report.html, output/preview.html を「パスワード必要」リダイレクトに置換
    print(f"[encrypt] replacing {REPORT_PATH.relative_to(PROJECT_ROOT)} with redirect ...")
    REPORT_PATH.write_text(REDIRECT_TEMPLATE, encoding="utf-8")
    if PREVIEW_PATH.exists():
        PREVIEW_PATH.write_text(REDIRECT_TEMPLATE, encoding="utf-8")

    print()
    print("=" * 60)
    print("✅ 暗号化完了")
    print(f"   パスワード: {password}")
    print(f"   公開URL: https://amtokyo713.github.io/vtuber-popularity-analysis/")
    print("=" * 60)


if __name__ == "__main__":
    main()
