## 修复

- 修复合并恢复后，未包含在备份中的本地文件被误标为「已备份」、随后可能被清理误删的问题。
- 修复旧输出路径失效时，恢复的 PNG 未重新关联到签发记录的问题。合并恢复仅在原输出缺失且文件校验值一致时补回关联。

**升级提示：** 旧版「已备份」标记会重置，文件和记录不会删除。请先做一次新备份，再使用「仅清理已备份文件」。换数据目录时，请在加密备份中勾选「同时备份水印密码」，恢复时选中设置，并用一条旧记录验证溯源。

## Fixes

- Merge restore no longer marks local files absent from the archive as backed up, preventing their accidental removal by backed-up-only cleanup.
- Restored PNGs are linked to their issuance records. Merge relinks an existing record only when its original output is missing and the restored file matches its checksum.

**Upgrade:** Old backup flags are reset without deleting any files or records. Make a fresh backup before using backed-up-only cleanup. If moving to a new data folder, opt in to include the watermark password in an encrypted backup, restore Settings, and verify an existing issuance.
