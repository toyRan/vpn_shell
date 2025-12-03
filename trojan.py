import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import os
import random
import string

# ========== 随机生成函数 ==========
def generate_random_port():
    """生成随机端口 (8000-9999)"""
    return str(random.randint(8000, 9999))

def generate_random_username():
    """生成10位随机用户名 (首字母必须是字母)"""
    first_char = random.choice(string.ascii_letters)
    remaining_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=9))
    return first_char + remaining_chars

def generate_random_password():
    """生成20位随机密码 (纯字母+数字，避免特殊符号导致Shell报错)"""
    # 去掉了 ! 和 &，防止 Linux Shell 误读为历史命令或后台符
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=20))

# ========== 自动填充 UI 的函数 ==========
def auto_generate_http_credentials():
    """自动生成HTTP代理的配置"""
    entry_http_port.delete(0, tk.END)
    entry_http_port.insert(0, generate_random_port())

    entry_http_username.delete(0, tk.END)
    entry_http_username.insert(0, generate_random_username())

    entry_http_password.delete(0, tk.END)
    entry_http_password.insert(0, generate_random_password())

def auto_generate_trojan_password():
    """自动生成Trojan密码"""
    entry_trojan_password.delete(0, tk.END)
    entry_trojan_password.insert(0, generate_random_password())

# ========== 核心逻辑：保存文件 (修复换行符) ==========
def save_script_to_file(content, default_name):
    """
    通用保存函数
    关键修复：强制将 Windows 的 \r\n 替换为 Linux 的 \n
    """
    # 1. 强制替换 Windows 换行符，防止 $'\r': command not found 错误
    content = content.replace('\r\n', '\n')
    
    file_path = filedialog.asksaveasfilename(
        defaultextension=".sh",
        filetypes=[("Shell Script", "*.sh"), ("All Files", "*.*")],
        initialfile=default_name,
        title="保存 Shell 脚本"
    )

    if file_path:
        try:
            # 2. 使用 newline='\n' 确保写入时也是 LF 格式
            with open(file_path, "w", encoding="utf-8", newline='\n') as f:
                f.write(content)
            messagebox.showinfo("成功", f"脚本已生成！\n\n保存在: {file_path}\n\n请上传到服务器后执行：\nbash {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件失败: {str(e)}")

# ========== 生成 Trojan 脚本 (已修改为 Let's Encrypt) ==========
def generate_trojan_script():
    domain = entry_trojan_domain.get().strip()
    port = entry_trojan_port.get().strip()
    password = entry_trojan_password.get().strip()

    if not domain or not port or not password:
        messagebox.showerror("错误", "所有字段都必须填写！")
        return

    if not port.isdigit():
        messagebox.showerror("错误", "端口必须是数字！")
        return

    # 注意：set +H 用于关闭历史扩展
    shell_content = f"""#!/bin/bash
# ==========================================
# 自动部署 Trojan (Docker版) - Let's Encrypt
# ==========================================
set +H

DOMAIN="{domain}"
PORT={port}
PASSWORD="{password}"

if [[ $EUID -ne 0 ]]; then
   echo "错误: 本脚本必须以 root 用户运行。" 
   exit 1
fi

echo ">>> [1/7] 安装基础工具..."
apt-get update
apt-get install -y ca-certificates curl gnupg socat lsof

echo ">>> [2/7] 安装 Docker..."
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \\
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \\
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \\
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl start docker
fi

echo ">>> [3/7] 准备目录..."
mkdir -p /etc/trojan

echo ">>> [4/7] 申请证书 (使用 Let's Encrypt)..."
# 确保 80 端口未被占用
if lsof -Pi :80 -sTCP:LISTEN -t >/dev/null ; then
    echo "停止占用 80 端口的服务..."
    systemctl stop nginx || true
    systemctl stop apache2 || true
fi

# 安装 acme.sh
curl https://get.acme.sh | sh
source ~/.bashrc

# === 关键修改：切换默认 CA 为 Let's Encrypt ===
# 这能解决 ZeroSSL 连接失败的问题，且不需要邮箱
/root/.acme.sh/acme.sh --set-default-ca --server letsencrypt

# 申请证书
/root/.acme.sh/acme.sh --issue -d "$DOMAIN" --standalone --force

# 安装证书到 /etc/trojan
/root/.acme.sh/acme.sh --install-cert -d "$DOMAIN" \\
--key-file       /etc/trojan/server.key  \\
--fullchain-file /etc/trojan/server.crt \\
--reloadcmd     "docker restart trojan"

echo ">>> [5/7] 生成配置..."
cat > /etc/trojan/config.json <<EOF
{{
    "run_type": "server",
    "local_addr": "0.0.0.0",
    "local_port": $PORT,
    "remote_addr": "127.0.0.1",
    "remote_port": 80,
    "password": [
        "$PASSWORD"
    ],
    "log_level": 1,
    "ssl": {{
        "cert": "/etc/trojan/server.crt",
        "key": "/etc/trojan/server.key",
        "cipher": "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384",
        "prefer_server_cipher": true,
        "alpn": [
            "http/1.1"
        ],
        "reuse_session": true,
        "session_ticket": false,
        "curves": ""
    }},
    "tcp": {{
        "no_delay": true,
        "keep_alive": true,
        "reuse_port": false,
        "fast_open": false,
        "fast_open_qlen": 20
    }}
}}
EOF

echo ">>> [6/7] 启动容器..."
docker rm -f trojan 2>/dev/null
docker run -d --name trojan --restart always --net host -v /etc/trojan:/etc/trojan teddysun/trojan

echo ">>> [7/7] 检查状态..."
sleep 2
if docker ps | grep -q trojan; then
    echo "=============================================="
    echo "部署完成 (Let's Encrypt 模式)!"
    echo "域名: $DOMAIN"
    echo "端口: $PORT"
    echo "密码: $PASSWORD"
    echo "=============================================="
else
    echo "错误：容器未启动，请使用 docker logs trojan 查看日志。"
fi
"""
    save_script_to_file(shell_content, "install_trojan.sh")

# ========== 生成 HTTP 代理脚本 ==========
def generate_http_proxy_script():
    port = entry_http_port.get().strip()
    username = entry_http_username.get().strip()
    password = entry_http_password.get().strip()

    if not port or not username or not password:
        messagebox.showerror("错误", "所有字段都必须填写！")
        return

    if not port.isdigit():
        messagebox.showerror("错误", "端口必须是数字！")
        return

    # 这里也要加 set +H 防止密码含有 ! 报错
    shell_content = f"""#!/bin/bash
# ==========================================
# 自动部署 HTTP代理 (gost Docker版)
# ==========================================
set +H

PORT={port}
USERNAME="{username}"
PASSWORD="{password}"

if [[ $EUID -ne 0 ]]; then
   echo "错误: 本脚本必须以 root 用户运行。"
   exit 1
fi

echo ">>> [1/3] 安装 Docker..."
apt-get update
apt-get install -y ca-certificates curl gnupg
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \\
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \\
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \\
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl start docker
fi

echo ">>> [2/3] 启动 HTTP 代理容器..."
# 如果旧容器存在则删除
docker rm -f http-proxy 2>/dev/null

# 使用 host 网络模式或者端口映射均可，这里用端口映射
docker run -d \\
    --name http-proxy \\
    --restart always \\
    -p $PORT:$PORT \\
    gogost/gost \\
    -L "http://$USERNAME:$PASSWORD@:$PORT"

echo ""
echo "=============================================="
echo "部署完成！"
echo "IP: $(curl -s ifconfig.me)"
echo "端口: $PORT"
echo "用户名: $USERNAME"
echo "密码: $PASSWORD"
echo "=============================================="
"""
    save_script_to_file(shell_content, "install_http_proxy.sh")

# ========== GUI 界面构建 ==========
root = tk.Tk()
root.title("全能代理部署脚本生成器 (Let's Encrypt 版)")
root.geometry("480x400")

# 样式微调
style = ttk.Style()
style.configure("TButton", padding=6)
style.configure("TLabel", font=("Arial", 10))

notebook = ttk.Notebook(root)
notebook.pack(fill='both', expand=True, padx=10, pady=10)

# ----------------- Trojan 页面 -----------------
frame_trojan = ttk.Frame(notebook)
notebook.add(frame_trojan, text="Trojan 部署")

tk.Label(frame_trojan, text="你的域名 (Domain):").pack(pady=(15, 5))
entry_trojan_domain = tk.Entry(frame_trojan, width=40)
entry_trojan_domain.pack()

tk.Label(frame_trojan, text="端口 (Port) [推荐 8443]:").pack(pady=(10, 5))
entry_trojan_port = tk.Entry(frame_trojan, width=40)
entry_trojan_port.insert(0, "8443")
entry_trojan_port.pack()

tk.Label(frame_trojan, text="连接密码 (Password):").pack(pady=(10, 5))
f_tj_pwd = tk.Frame(frame_trojan)
f_tj_pwd.pack()
entry_trojan_password = tk.Entry(f_tj_pwd, width=30)
entry_trojan_password.pack(side='left', padx=5)
tk.Button(f_tj_pwd, text="随机", command=auto_generate_trojan_password, bg="#FF9800", fg="white").pack(side='left')

tk.Button(frame_trojan, text="生成 install_trojan.sh", command=generate_trojan_script, bg="#4CAF50", fg="white", font=("Arial", 11, "bold")).pack(pady=25, fill='x', padx=50)


# ----------------- HTTP 代理页面 -----------------
frame_http = ttk.Frame(notebook)
notebook.add(frame_http, text="HTTP 代理部署")

tk.Label(frame_http, text="端口 (Port):").pack(pady=(15, 5))
entry_http_port = tk.Entry(frame_http, width=40)
entry_http_port.insert(0, "8080")
entry_http_port.pack()

tk.Label(frame_http, text="用户名 (Username):").pack(pady=(5, 5))
entry_http_username = tk.Entry(frame_http, width=40)
entry_http_username.pack()

tk.Label(frame_http, text="密码 (Password):").pack(pady=(5, 5))
entry_http_password = tk.Entry(frame_http, width=40)
entry_http_password.pack()

# 按钮容器
f_http_btns = tk.Frame(frame_http)
f_http_btns.pack(pady=20)

tk.Button(f_http_btns, text="🎲 一键随机生成配置", command=auto_generate_http_credentials, bg="#FF9800", fg="white", width=20).grid(row=0, column=0, padx=10)
tk.Button(frame_http, text="生成 install_http_proxy.sh", command=generate_http_proxy_script, bg="#2196F3", fg="white", font=("Arial", 11, "bold")).pack(fill='x', padx=50, pady=10)

root.mainloop()