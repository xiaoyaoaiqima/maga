import argparse
import os
import subprocess
import zipfile
import json
import sys
import shutil
from datetime import datetime

def run_command(command, cwd=None):
    print(f"执行命令: {command}")
    result = subprocess.run(command, shell=True, cwd=cwd)
    if result.returncode != 0:
        print(f"命令执行失败: {command}")
        return False
    return True

def scp_and_deploy(archive_name, config, target_path):
    """执行 SCP 上传和远程部署"""
    ssh_conf = config["ssh"]
    ssh_target = f"{ssh_conf['username']}@{ssh_conf['host']}"
    ssh_port_arg = f"-p {ssh_conf['port']}" if ssh_conf.get('port') else ""
    scp_port_arg = f"-P {ssh_conf['port']}" if ssh_conf.get('port') else ""

    remote_zip_path = f"{target_path}/dist.zip"

    print(f"\n--- 正在部署至: {target_path} ---")

    # 1. 确保远程目录存在
    mkdir_cmd = f"ssh {ssh_port_arg} {ssh_target} 'mkdir -p {target_path}'"
    if not run_command(mkdir_cmd): return False

    # 2. 上传文件
    print(f"上传文件到: {remote_zip_path}")
    scp_cmd = f"scp {scp_port_arg} {archive_name} {ssh_target}:{remote_zip_path}"
    if not run_command(scp_cmd): return False

    # 3. 远程备份、解压
    print(f"正在远程备份 (目标目录: {target_path})...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{target_path}/backups"

    # 这里的逻辑是：
    # 1. 创建 backups 文件夹
    # 2. 如果已存在 dist 目录，则将其打包并移动到 backups 文件夹下，然后删除原 dist 目录
    # 3. 解压新的压缩包到 dist 目录
    remote_cmds = [
        f"mkdir -p {backup_dir}",
        f"cd {target_path}",
        f"if [ -d dist ]; then tar -czf {backup_dir}/dist_{timestamp}.tar.gz dist && rm -rf dist; fi",
        f"unzip -o dist.zip -d dist",
        f"rm -f dist.zip"
    ]
    remote_shell_cmd = " && ".join(remote_cmds)
    ssh_exec_cmd = f"ssh {ssh_port_arg} {ssh_target} \"{remote_shell_cmd}\""
    if not run_command(ssh_exec_cmd): return False

    print(f"部署完成: {target_path}")
    return True

def main():
    # 获取脚本目录和配置
    script_dir = os.path.dirname(os.path.abspath(__file__))
    frontend_dir = os.path.dirname(script_dir)
    app_dir = os.path.join(frontend_dir, "apps/raap-admin")
    dist_dir = os.path.join(app_dir, "dist")
    config_path = os.path.join(script_dir, "config.json")

    if not os.path.exists(config_path):
        print(f"错误: 找不到配置文件 {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        full_config = json.load(f)

    print("=== MAGA Console 前端交互式部署工具 ===")

    # 1. 选择环境配置
    envs = list(full_config.keys())
    print("\n可用配置环境:")
    for i, env in enumerate(envs):
        print(f"  [{i+1}] {env}")

    try:
        env_idx = int(input(f"请选择配置环境 (1-{len(envs)}, 默认 1): ") or 1) - 1
        selected_env = envs[env_idx]
    except (ValueError, IndexError):
        print("无效的选择")
        sys.exit(1)

    config = full_config[selected_env]
    targets = config.get("targets", {})

    # 2. 构建
    print(f"\n--- 正在构建 {selected_env} 环境 ---")
    if os.path.exists(dist_dir):
        print(f"清理历史构建目录: {dist_dir}")
        shutil.rmtree(dist_dir)

    if not run_command("pnpm turbo build --filter=@maga/console", cwd=frontend_dir):
        sys.exit(1)

    # 3. 本地预览验证
    print(f"\n--- 构建完成，正在自动启动本地预览 ---")
    preview_proc = subprocess.Popen(
        ["pnpm", "preview"],
        cwd=app_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT
    )
    print(f"预览服务已启动 (http://localhost:4173)")

    try:
        confirm = input("预览效果正常吗？(y/n): ")
        if confirm.lower() != 'y':
            print("部署已中止。")
            preview_proc.terminate()
            sys.exit(0)
    finally:
        preview_proc.terminate()
        try:
            preview_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            preview_proc.kill()

    # 4. 打包
    archive_name = f"dist_tmp.zip"
    print(f"\n--- 正在打包 ---")
    if not os.path.exists(dist_dir):
        print(f"错误: 构建产物目录 {dist_dir} 不存在")
        sys.exit(1)

    with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir)
                zipf.write(file_path, arcname)

    # 5. 部署逻辑
    try:
        if not targets:
            # 如果没有 targets 配置，尝试回退到硬编码或手动输入
            print("警告: 配置文件中未定义具体 targets")
            target_path = input("请输入远程部署目录路径: ")
            if target_path:
                scp_and_deploy(archive_name, config, target_path)
        else:
            while True:
                print("\n选择部署目标:")
                target_keys = list(targets.keys())
                for i, k in enumerate(target_keys):
                    print(f"  [{i+1}] {k} ({targets[k]})")
                print(f"  [{len(target_keys)+1}] 全部按顺序部署 (先个人测试 -> 后正式环境)")
                print(f"  [q] 退出")

                choice = input("请选择 (1-3 或 q): ").lower()

                if choice == 'q':
                    break
                elif choice == str(len(target_keys) + 1):
                    # 顺序部署流程
                    print("\n>>> 步骤 1: 部署到个人测试环境")
                    if scp_and_deploy(archive_name, config, targets["personal"]):
                        print("\n个人环境部署成功！请在浏览器访问测试。")
                        confirm = input("测试通过，现在部署到正式环境吗？(y/n): ")
                        if confirm.lower() == 'y':
                            print("\n>>> 步骤 2: 部署到正式环境")
                            scp_and_deploy(archive_name, config, targets["official"])
                    break
                else:
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(target_keys):
                            scp_and_deploy(archive_name, config, targets[target_keys[idx]])
                            break
                        else:
                            print("无效选择")
                    except ValueError:
                        print("无效选择")
    finally:
        if os.path.exists(archive_name):
            os.remove(archive_name)
        print("\n脚本运行结束。")

if __name__ == "__main__":
    main()
