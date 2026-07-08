# RoboFont Development Notes

This repository should prefer official RoboFont APIs and documented extension patterns wherever possible. Scripts can use supporting libraries such as FontParts, Vanilla, and Defcon when they match the task, but RoboFont behavior should be verified against RoboFont documentation or local source before it is treated as stable.

## Reference Links

- [RoboFont documentation](https://doc.robofont.com/)
- [RoboFont API/reference documentation](https://www.robofont.com/documentation/reference/)
- [RoboFont how-tos](https://doc.robofont.com/documentation/how-tos/)
- [RoboFont extensions topic](https://doc.robofont.com/documentation/topics/extensions/)
- [RoboFont extension file specification](https://robofont.com/documentation/reference/extensions/extension-file-spec/)
- [Creating extensions tutorial](https://robofont.com/documentation/tutorials/creating-extensions/)
- [FontParts documentation](https://fontparts.robotools.dev/)
- [Vanilla documentation](https://vanilla.robotools.dev/)
- [Defcon documentation](https://defcon.robotools.dev/)
- RoboFont Subscriber documentation: verify availability in the current RoboFont
  docs or installed RoboFont resources before relying on it.

## Working Rules For Codex

- Do not invent RoboFont APIs.
- Prefer small runnable scripts before packaging behavior as extensions.
- Keep machine-specific paths out of version control.
- Put local paths and configuration in ignored local config files.
- Comment any AppKit or macOS-specific window-management code.
- Treat xTools integration as experimental unless verified from source.
