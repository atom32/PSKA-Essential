# Legacy Diagnostic Demo Disabled

这个目录是历史素材，只能说明当时 PSKA Product API 本地诊断页的 smoke path。

它不是 Hermes WebUI extension 演示，也不是 PSKA 的独立产品前端。旧录制、构建、旁白、打包脚本已经被硬禁用。

当前产品演示入口：

```bash
node scripts/record_hermes_pska_extension_demo.cjs
python3 scripts/verify_hermes_extension_demo_pack.py --require-video
```

当前可交付素材在：

```text
demo/browser/hermes_pska_extension_demo/
```
