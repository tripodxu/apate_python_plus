import os
import sys
import json
import random
import struct
import subprocess
import shutil
import secrets
from pathlib import Path

DEFAULT_MAGIC = b"DGSK"
CONFIG_FILE_NAME = "mask_config.json"

class DisguiseError(Exception):
    pass

# =================== 基础工具函数 ===================
def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILE_NAME

def normalize_config(data) -> dict:
    if not isinstance(data, dict): data = {}
    mask_library = data.get("mask_library", [])
    if not isinstance(mask_library, list): mask_library = []
    magic_hex = data.get("magic_hex", DEFAULT_MAGIC.hex())
    if not isinstance(magic_hex, str): magic_hex = DEFAULT_MAGIC.hex()
    try:
        magic_bytes = bytes.fromhex(magic_hex)
        if not (1 <= len(magic_bytes) <= 32): magic_hex = DEFAULT_MAGIC.hex()
    except Exception:
        magic_hex = DEFAULT_MAGIC.hex()
    return {"mask_library": mask_library, "magic_hex": magic_hex}

def load_config() -> dict:
    config_path = get_config_path()
    if not config_path.exists(): return normalize_config({})
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return normalize_config(data)
    except Exception:
        return normalize_config({})

def save_config(config: dict):
    config = normalize_config(config)
    with open(get_config_path(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def magic_to_display_text(magic: bytes) -> str:
    try: ascii_part = magic.decode("utf-8")
    except Exception: ascii_part = "<非UTF-8字节序列>"
    return f"HEX={magic.hex().upper()} | BYTES={magic!r} | TEXT={ascii_part}"

def build_non_conflicting_path(target_path: Path, tag: str, reserved_paths=None) -> Path:
    target_path = Path(target_path)
    reserved = {str(Path(p).resolve()) for p in (reserved_paths or [])}
    resolved_target = str(target_path.resolve())
    if resolved_target not in reserved and not target_path.exists():
        return target_path
    stem = target_path.stem
    suffix = target_path.suffix
    index = 1
    while True:
        candidate = target_path.with_name(f"{stem}_{tag}_{index}{suffix}")
        resolved_candidate = str(candidate.resolve())
        if resolved_candidate not in reserved and not candidate.exists():
            return candidate
        index += 1

def collect_files_from_paths(paths):
    results, seen = [], set()
    for p in paths:
        path = Path(p)
        if not path.exists(): continue
        if path.is_file():
            s = str(path.resolve())
            if s not in seen:
                seen.add(s), results.append(s)
        elif path.is_dir():
            for sub in path.rglob("*"):
                if sub.is_file():
                    s = str(sub.resolve())
                    if s not in seen:
                        seen.add(s), results.append(s)
    return results

# =================== 文件操作核心 ===================
def parse_disguised_metadata(file_obj, file_size: int, magic: bytes):
    file_obj.seek(-len(magic), os.SEEK_END)
    if file_obj.read(len(magic)) != magic:
        raise DisguiseError("文件尾标记无效")

    try:
        if file_size >= len(magic) + 8 + 4 + 1:
            file_obj.seek(-(len(magic) + 8), os.SEEK_END)
            original_size = struct.unpack("<Q", file_obj.read(8))[0]
            file_obj.seek(-(len(magic) + 8 + 4), os.SEEK_END)
            head_len = struct.unpack("<I", file_obj.read(4))[0]
            file_obj.seek(-(len(magic) + 8 + 4 + 1), os.SEEK_END)
            name_len = struct.unpack("B", file_obj.read(1))[0]

            name_pos = file_size - len(magic) - 8 - 4 - 1 - name_len
            head_pos = name_pos - head_len
            if 0 <= name_pos <= file_size and 0 <= head_pos <= file_size:
                file_obj.seek(name_pos)
                raw_name = file_obj.read(name_len)
                decoded = raw_name.decode("utf-8")
                candidate = Path(decoded).name
                if candidate and candidate == decoded and decoded not in (".", ".."):
                    return {"format": "v2", "head_len": head_len, "name_len": name_len,
                            "name_pos": name_pos, "head_pos": head_pos,
                            "original_name": candidate, "original_size": original_size}
    except Exception: pass

    file_obj.seek(-(len(magic) + 4), os.SEEK_END)
    head_len = struct.unpack("<I", file_obj.read(4))[0]
    file_obj.seek(-(len(magic) + 4 + 1), os.SEEK_END)
    name_len = struct.unpack("B", file_obj.read(1))[0]
    if name_len > file_size: raise DisguiseError("文件结构异常：名称长度非法")
    name_pos = file_size - len(magic) - 4 - 1 - name_len
    if name_pos < 0: raise DisguiseError("文件结构异常：name_pos 非法")
    head_pos = name_pos - head_len
    if head_pos < 0: raise DisguiseError("文件结构异常：head_pos 非法")
    file_obj.seek(name_pos)
    raw_name = file_obj.read(name_len)
    if len(raw_name) != name_len: raise DisguiseError("文件结构异常：名称长度不足")
    try:
        decoded = raw_name.decode("utf-8")
        candidate = Path(decoded).name
        if candidate and candidate == decoded and decoded not in (".", ".."):
            original_name = candidate
        else: raise ValueError("不是完整文件名")
    except Exception:
        try: original_suffix = raw_name.decode("utf-8")
        except Exception as e: raise DisguiseError(f"无法解析原始文件名/后缀：{e}")
        original_name = Path(file_obj.name).stem + original_suffix

    return {"format": "v1", "head_len": head_len, "name_len": name_len,
            "name_pos": name_pos, "head_pos": head_pos, "original_name": original_name,
            "original_size": head_pos}

def is_disguised_file(file_path: str, magic: bytes) -> bool:
    path = Path(file_path)
    if not path.is_file(): return False
    try:
        if path.stat().st_size < (1 + 4 + len(magic)): return False
        with open(path, "rb") as f:
            f.seek(-len(magic), os.SEEK_END)
            return f.read(len(magic)) == magic
    except Exception: return False

def disguise_file(file_path: str, mask_path: str, magic: bytes, reserved_output_paths=None) -> str:
    file_path, mask_path = Path(file_path), Path(mask_path)
    if not file_path.is_file(): raise FileNotFoundError(f"目标不存在: {file_path}")
    if is_disguised_file(str(file_path), magic): raise DisguiseError("已经是伪装态")

    with open(mask_path, "rb") as f: mask_bytes = f.read()
    if not mask_bytes: raise DisguiseError("面具文件为空")

    mask_len = len(mask_bytes)
    original_file_name_bytes = file_path.name.encode("utf-8")
    if len(original_file_name_bytes) > 255: raise DisguiseError("文件名过长")
    original_size = file_path.stat().st_size

    with open(file_path, "r+b") as f:
        original_head = f.read(mask_len)
        f.seek(0)
        f.write(mask_bytes)
        f.seek(0, os.SEEK_END)
        f.write(original_head[::-1])
        f.write(original_file_name_bytes)
        f.write(struct.pack("B", len(original_file_name_bytes)))
        f.write(struct.pack("<I", len(original_head)))
        f.write(struct.pack("<Q", original_size))
        f.write(magic)

    desired_path = file_path.with_suffix(mask_path.suffix)
    disguised_path = build_non_conflicting_path(desired_path, "disguised", reserved_output_paths)
    os.replace(str(file_path), str(disguised_path))
    return str(disguised_path)

def reveal_file(file_path: str, magic: bytes, reserved_output_paths=None) -> str:
    file_path = Path(file_path)
    if not is_disguised_file(str(file_path), magic): raise DisguiseError("非当前魔术字对应伪装文件")

    with open(file_path, "r+b") as f:
        meta = parse_disguised_metadata(f, file_path.stat().st_size, magic)
        f.seek(meta["head_pos"])
        original_head = f.read(meta["head_len"])[::-1]
        f.seek(0)
        f.write(original_head)
        f.truncate(meta["original_size"])

    desired_path = file_path.parent / meta["original_name"]
    restored_path = desired_path
    if str(desired_path.resolve()) in {str(Path(p).resolve()) for p in (reserved_output_paths or [])}:
        restored_path = build_non_conflicting_path(desired_path, "restored", reserved_output_paths)
    os.replace(str(file_path), str(restored_path))
    return str(restored_path)


# =================== 引擎状态类 ===================
class DisguiseEngine:
    def __init__(self):
        self.config = load_config()
        self.target_files = []
        self.mask_library = []
        self._load_mask_library_from_config()

    def _load_mask_library_from_config(self):
        library = self.config.get("mask_library", [])
        self.mask_library = [s for s in (str(Path(p).resolve()) for p in library) if Path(s).is_file()]
        self.save_config()

    def save_config(self):
        self.config["mask_library"] = self.mask_library[:]
        save_config(self.config)

    def get_magic_bytes(self) -> bytes:
        try:
            magic = bytes.fromhex(self.config.get("magic_hex", DEFAULT_MAGIC.hex()))
            return magic if (1 <= len(magic) <= 32) else DEFAULT_MAGIC
        except Exception: return DEFAULT_MAGIC

    def parse_and_set_magic(self, raw_text: str) -> bytes:
        text = (raw_text or "").strip()
        if not text: raise DisguiseError("请输入魔术字")
        compact = text.replace(" ", "").replace("\n", "").replace("\t", "")
        if compact.lower().startswith("0x"): compact = compact[2:]

        if compact and all(ch in "0123456789abcdefABCDEF" for ch in compact) and len(compact) % 2 == 0:
            data = bytes.fromhex(compact)
        else:
            data = text.encode("utf-8")

        if not (1 <= len(data) <= 32): raise DisguiseError("长度必须在 1 到 32 字节之间")
        self.config["magic_hex"] = data.hex()
        self.save_config()
        return data

    def generate_random_magic(self) -> bytes:
        magic = secrets.token_bytes(4)
        self.config["magic_hex"] = magic.hex()
        self.save_config()
        return magic

    def reset_magic(self) -> bytes:
        self.config["magic_hex"] = DEFAULT_MAGIC.hex()
        self.save_config()
        return DEFAULT_MAGIC

    def get_common_target_parent_dir(self) -> Path:
        if not self.target_files: raise DisguiseError("没有目标文件")
        resolved = [Path(p).resolve() for p in self.target_files if Path(p).is_file()]
        if not resolved: raise DisguiseError("目标列表中没有有效文件")
        try: common_dir = Path(os.path.commonpath([str(p.parent) for p in resolved]))
        except ValueError: raise DisguiseError("不在可计算公共目录的结构中")
        if not common_dir.exists() or not common_dir.is_dir(): raise DisguiseError("目录无效")
        return common_dir

    def get_random_mask_file(self) -> str:
        self.mask_library = [p for p in self.mask_library if Path(p).is_file()]
        self.save_config()
        if not self.mask_library: raise DisguiseError("面具库为空")
        return random.choice(self.mask_library)

    def detect_status(self, progress_cb, log_cb, process_events_cb):
        magic = self.get_magic_bytes()
        disguised_count, original_count, failed = 0, 0, []
        total = len(self.target_files)
        
        log_cb(f"开始检测，魔术字：{magic_to_display_text(magic)}")
        progress_cb(0, total, "正在检测文件状态...", f"0/{total}")

        for index, path in enumerate(self.target_files, start=1):
            try:
                if is_disguised_file(path, magic):
                    disguised_count += 1
                    log_cb(f"[伪装态] {path}")
                else:
                    original_count += 1
                    log_cb(f"[原始态] {path}")
            except Exception as e: failed.append(f"{path} -> {e}")
            progress_cb(index, total, "正在检测...", f"{index}/{total}")
            process_events_cb()

        return original_count, disguised_count, failed

    def handle_toggle(self, progress_cb, log_cb, process_events_cb):
        magic = self.get_magic_bytes()
        need_mask = any(not is_disguised_file(p, magic) for p in self.target_files)
        if need_mask and not self.mask_library:
            raise DisguiseError("存在需伪装文件，但面具库为空")

        reserved_outputs = {str(Path(p).resolve()) for p in self.target_files if Path(p).exists()}
        success, failed = 0, []
        total = len(self.target_files)

        log_cb(f"执行自动切换，魔术字：{magic_to_display_text(magic)}")
        progress_cb(0, total, "正在批处理...", f"0/{total}")

        for index, old_path in enumerate(self.target_files[:], start=1):
            try:
                reserved_outputs.discard(str(Path(old_path).resolve()))
                if is_disguised_file(old_path, magic):
                    log_cb(f"准备还原：{old_path}")
                    new_path = reveal_file(old_path, magic, reserved_outputs)
                    log_cb(f"还原完成：{new_path}")
                else:
                    mask_file = self.get_random_mask_file()
                    log_cb(f"准备伪装(使用 {mask_file})：{old_path}")
                    new_path = disguise_file(old_path, mask_file, magic, reserved_outputs)
                    log_cb(f"伪装完成：{new_path}")

                self.target_files[index-1] = str(Path(new_path).resolve())
                reserved_outputs.add(self.target_files[index-1])
                success += 1
            except Exception as e:
                reserved_outputs.add(str(Path(old_path).resolve()))
                failed.append(f"{old_path} -> {e}")
                log_cb(f"失败：{old_path} -> {e}")

            progress_cb(index, total, "正在批处理...", f"已处理 {index}/{total}")
            process_events_cb()

        return success, failed

# ==== 获取真实的 Python 解释器路径 ====
    def _get_real_python(self) -> str:
        # 1. 如果是以源码 (.py) 形式运行，sys.executable 就是绝对路径，无视 PATH 环境变量
        if not getattr(sys, "frozen", False):
            return sys.executable
            
        # 2. 如果当前程序本身已经被打包成了 EXE (此时 sys.executable 指向本程序自己)
        # 则需要在小白的电脑上寻找是否安装了 Python
        if shutil.which("python"):
            return "python"
        if shutil.which("py"): # Windows 自带的 Python 启动器，通常在全局 PATH 里
            return "py"
            
        raise DisguiseError(
            "当前工具运行在独立 EXE 模式，但在您的电脑上未检测到 Python 环境。\n"
            "【生成恢复 EXE】功能底层依赖 Python 编译器，请先下载安装 Python！"
        )

    # ==== 环境检测与自动安装 PyInstaller ====
    def _ensure_pyinstaller(self, log_cb, python_exe: str):
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

        try:
            res = subprocess.run(
                [python_exe, "-m", "PyInstaller", "--version"], 
                capture_output=True, text=True, **kwargs
            )
            if res.returncode == 0:
                return  # 已安装，正常退出
        except Exception:
            pass

        log_cb("⚠️ 未检测到 PyInstaller 模块。")
        log_cb("⏳ 正在自动调用清华镜像源为您安装，请耐心等待（通常需十秒左右，期间界面可能轻微卡顿）...")
        
        try:
            subprocess.run(
                [python_exe, "-m", "pip", "install", "pyinstaller", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                check=True, capture_output=True, text=True, **kwargs
            )
            log_cb("✅ PyInstaller 全自动安装成功！")
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr if e.stderr else e.stdout
            log_cb(f"❌ 自动安装失败:\n{err_msg}")
            raise DisguiseError("自动安装 PyInstaller 失败，请检查网络或以管理员身份手动运行安装命令。")

    # ==== 打包 EXE 方法 ====
    def generate_restore_exe(self, output_dir: Path, log_cb):
        # 0. 寻找真实的 Python 解释器（无视 PATH 环境变量）
        python_exe = self._get_real_python()

        # 1. 自动检测并安装所需环境
        self._ensure_pyinstaller(log_cb, python_exe)

        # 2. 生成临时脚本
        magic = self.get_magic_bytes()
        script_name = "restore_all_disguised.py"
        py_script_path = get_app_dir() / script_name

        script_content = f'''import sys\nimport os\nimport struct\nfrom pathlib import Path\nMAGIC = bytes.fromhex("{magic.hex()}")\n'''
        script_content += '''
def get_base_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent

def is_disguised_file(p: Path) -> bool:
    try:
        if p.stat().st_size < (1+4+len(MAGIC)): return False
        with open(p, "rb") as f:
            f.seek(-len(MAGIC), os.SEEK_END)
            return f.read(len(MAGIC)) == MAGIC
    except Exception: return False

def parse_metadata(f, sz):
    f.seek(-len(MAGIC), os.SEEK_END)
    if f.read(len(MAGIC)) != MAGIC: raise Exception("标记无效")
    try:
        if sz >= len(MAGIC)+13:
            f.seek(-(len(MAGIC)+8), os.SEEK_END)
            osize = struct.unpack("<Q", f.read(8))[0]
            f.seek(-(len(MAGIC)+12), os.SEEK_END)
            hlen = struct.unpack("<I", f.read(4))[0]
            f.seek(-(len(MAGIC)+13), os.SEEK_END)
            nlen = struct.unpack("B", f.read(1))[0]
            npos, hpos = sz - len(MAGIC) - 13 - nlen, sz - len(MAGIC) - 13 - nlen - hlen
            if 0 <= npos <= sz and 0 <= hpos <= sz:
                f.seek(npos)
                name = Path(f.read(nlen).decode("utf-8")).name
                if name and name not in (".", ".."): return {"hlen": hlen, "hpos": hpos, "name": name, "osize": osize}
    except Exception: pass
    f.seek(-(len(MAGIC)+4), os.SEEK_END)
    hlen = struct.unpack("<I", f.read(4))[0]
    f.seek(-(len(MAGIC)+5), os.SEEK_END)
    nlen = struct.unpack("B", f.read(1))[0]
    npos, hpos = sz - len(MAGIC) - 5 - nlen, sz - len(MAGIC) - 5 - nlen - hlen
    f.seek(npos)
    try: name = Path(f.read(nlen).decode("utf-8")).name
    except Exception: name = Path(f.name).stem + f.read(nlen).decode("utf-8")
    return {"hlen": hlen, "hpos": hpos, "name": name, "osize": hpos}

def reveal_file(fp: Path, reserved):
    with open(fp, "r+b") as f:
        meta = parse_metadata(f, fp.stat().st_size)
        f.seek(meta["hpos"])
        head = f.read(meta["hlen"])[::-1]
        f.seek(0)
        f.write(head)
        f.truncate(meta["osize"])
    dp = fp.parent / meta["name"]
    rest = dp
    if str(dp.resolve()) in reserved:
        idx = 1
        while True:
            c = dp.with_name(f"{dp.stem}_restored_{idx}{dp.suffix}")
            if str(c.resolve()) not in reserved and not c.exists():
                rest = c; break
            idx += 1
    fp.replace(rest)
    return rest

def main():
    bd = get_base_dir()
    print(f"扫描: {bd}\\n魔术字: {MAGIC.hex()}\\n"+"-"*40)
    res, fail = 0, 0
    reserved = {str(p.resolve()) for p in bd.rglob("*") if p.is_file()}
    for p in bd.rglob("*"):
        if p.is_file() and p.name.lower() not in {"restore_all_disguised.exe", "restore_all_disguised.py"}:
            try:
                reserved.discard(str(p.resolve()))
                if is_disguised_file(p):
                    np = reveal_file(p, reserved)
                    reserved.add(str(np.resolve()))
                    res += 1
                    print(f"[恢复] {p.name} -> {np.name}")
            except Exception as e: fail += 1; print(f"[失败] {p.name} -> {e}")
    print(f"\\n完成: 成功 {res}, 失败 {fail}")
    input("按回车退出...")

if __name__ == "__main__": main()
'''
        try:
            with open(py_script_path, "w", encoding="utf-8") as f:
                f.write(script_content)
            
            output_dir.mkdir(parents=True, exist_ok=True)
            build_dir = output_dir / "build_pyinstaller_restore"
            spec_dir = output_dir / "spec_pyinstaller_restore"
            exe_name = py_script_path.stem + ".exe"
            dist_path = output_dir / exe_name

            # 3. 准备打包含参数（同样隐藏黑框）
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)

            log_cb(f"🚀 执行 Pyinstaller 开始打包...")
            subprocess.run([
                python_exe, "-m", "PyInstaller", "--onefile", "--distpath", str(output_dir),
                "--workpath", str(build_dir), "--specpath", str(spec_dir), str(py_script_path)
            ], check=True, **kwargs)

            # 4. 清理临时缓存
            shutil.rmtree(build_dir, ignore_errors=True)
            shutil.rmtree(spec_dir, ignore_errors=True)
            shutil.rmtree(py_script_path.parent / "__pycache__", ignore_errors=True)
            if (spec_dir / f"{py_script_path.stem}.spec").exists():
                (spec_dir / f"{py_script_path.stem}.spec").unlink()
            
            return dist_path
        finally:
            if py_script_path.exists(): py_script_path.unlink()