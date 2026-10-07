# Office 就地编辑：document_patch

日期：2026-10-07  
状态：已实现

## 目标

已有 docx/xlsx/pptx 支持就地修改，不再只能 `create_*` 整篇重写。

## 工具

- `document_edit`：`mode=rewrite`（默认）行为不变。
- `document_edit(mode=in_place)`：明确引导用 `document_patch`（不做不可靠的整篇覆盖）。
- `document_patch`：`open_file` + 细粒度 SDK + `save_file`。

| format | ops | SDK |
|--------|-----|-----|
| docx | `find_replace` | `doc_find_and_replace`（回退 `doc_replace_text`） |
| xlsx | `set_csv` / `replace` | `sheet_set_range_value_by_csv` / `sheet_replace` |
| pptx | `find_replace` | `slide_find_replace_text` |

## file_id 缓存

`path → file_id` 短期缓存（`bridge._FILE_ID_CACHE`）。preview / patch / rewrite 写入后可复用。

## 用法

```
document_patch(
  file_path="/abs/a.docx",
  ops=[{"op":"find_replace","find":"旧","replace":"新"}]
)
```
