# 粤语粵拼数据来源与许可

转换后的 `yue_jyutping` 词库和输入法表源自 [Zytos60/rime-cantonese](https://github.com/Zytos60/rime-cantonese)，其中的粵拼数据由 Cantonese Computational Linguistics Infrastructure Development Workgroup（CanCLID）及贡献者维护。

- 上游版本：`259f0e48bba840c3a2e0d117539e96937f3d89bc`
- 使用文件：`jyut6ping3.words.dict.yaml`、`jyut6ping3.chars.dict.yaml`、`jyut6ping3.phrase.dict.yaml`、`jyut6ping3.schema.yaml`
- 上游许可：Creative Commons Attribution 4.0 International（CC BY 4.0）
- 许可文本：https://creativecommons.org/licenses/by/4.0/
- 转换方式：提取并过滤汉字词条和带调粵拼；将字符表、词表及可无歧义组合的短语转换为 Clink 的读音到候选 TSV。复合读音和组合短语受默认数量上限约束。

原始 Rime YAML 文件不作为 Clink 资源发布。重新生成源文件：

```sh
python3 tools/convert_rime_cantonese.py /path/to/rime-cantonese
```