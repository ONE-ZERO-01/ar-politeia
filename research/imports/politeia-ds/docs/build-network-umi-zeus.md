# UMI / Zeus 环境下的构建与依赖拉取（无外网）

## 背景

- **UMI 服务器**：通常**无法访问外网**，CMake 在配置/构建测试目标时，会通过 `FetchContent` 从 **GitHub** 克隆 **GoogleTest**（见 `tests/CMakeLists.txt`，标签 `v1.14.0`）。在 UMI 上执行 `cmake` 时会出现类似错误：
  - `fatal: unable to access 'https://github.com/google/googletest.git/'`
  - 或连接超时、HTTP2 错误等。

- **Zeus 服务器**：与 UMI **挂载同一套文件系统**（工程路径在两边一致）。Zeus 侧**可以访问外网**，适合完成首次依赖下载与需要联网的 CMake 步骤。

结论：**在 Zeus 上进入本仓库对应目录执行配置与构建**，把 `build/`（或至少 `build/_deps/googletest-src` 等由 FetchContent 生成的内容）准备好后，UMI 上即可在同一路径下继续编译、运行（无需再次访问 GitHub）。

---

## 推荐流程（首次或 `build` 需重新生成依赖时）

1. **在可联网的机器上登录 Zeus**（示例）：
   ```bash
   ssh zeus
   ```

2. **进入与 UMI 相同的仓库路径**（请按实际挂载路径替换）：
   ```bash
   cd /path/to/civil
   ```

3. **配置并构建**（会拉取 googletest；仅需成功完成一次配置即可）：
   ```bash
   cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
   cmake --build build -j"$(nproc)"
   ```

4. **运行测试（可选）**：
   ```bash
   ctest --test-dir build --output-on-failure
   ```

5. **回到 UMI**：若 `build` 在共享盘上且路径一致，一般可直接：
   ```bash
   cd /path/to/civil
   cmake --build build -j"$(nproc)"
   ./build/src/politeia examples/adam_eve_quick.cfg
   ```
   若 UMI 上**新建了另一套 `build` 目录**且该目录不在 Zeus 已填充的共享位置，则仍需在 Zeus 上对**同一 `build` 路径**执行一次 `cmake`，或把已下载好的 `_deps` 拷到对应 `build` 下（不推荐手工维护，优先统一使用共享盘上的单一 `build`）。

---

## 涉及的外部依赖

| 依赖 | 来源 | 用途 |
|------|------|------|
| GoogleTest | `https://github.com/google/googletest.git` 标签 `v1.14.0` | 单元测试（`POLITEIA_BUILD_TESTS=ON` 时） |

主程序 `politeia` 本身不依赖从 GitHub 拉取的库；**仅开启测试时**需要上述克隆。

---

## Python 脚本（初始条件生成）

`scripts/generate_genesis.py` 依赖 **NumPy**，与 CMake 无关。若 UMI 不能 `pip install`，可在 Zeus 上生成 `.csv` 后于 UMI 使用；或在 UMI 使用系统包：`apt install python3-numpy`（若镜像源可用）。

---

## 排查要点

- **仍报无法连接 github.com**：确认当前终端在 **Zeus** 上，且当前目录是共享盘上的仓库路径。
- **Zeus 已构建、UMI 仍拉取失败**：检查 UMI 是否用了**另一份** `build` 目录；统一到 Zeus 已执行过 `cmake` 的那份路径。
- **仅需主程序、不需要测试**：配置时关闭测试即可**完全避免**拉取 GoogleTest：
  ```bash
  cmake -S . -B build -DPOLITEIA_BUILD_TESTS=OFF
  cmake --build build -j"$(nproc)"
  ```
  默认 `POLITEIA_BUILD_TESTS=ON`，会触发 `FetchContent`。

---

*文档目的：沉淀 UMI 无外网时通过 Zeus 拉取 GitHub 依赖的操作约定，避免重复踩坑。*

相关运维文档：[[docs/server-config]]（拓扑、SSH、项目路径与 GPU 使用流程）。
