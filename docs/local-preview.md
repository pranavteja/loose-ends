# Local document preview on Debian

Open the entire repository folder in VS Code, then open a Markdown file and press Ctrl+Shift+V. Ctrl+K followed by V opens the preview beside the source. Relative SVG links resolve against the Markdown file. Enable Mermaid preview support for the installed editor version if diagrams appear as code.

You can also open individual wireframes directly:

```bash
xdg-open ~/Documents/loose-ends/docs/wireframes/home.svg
xdg-open ~/Documents/loose-ends/docs/wireframes/review.svg
xdg-open ~/Documents/loose-ends/docs/wireframes/mobile.svg
```

A browser does not generally render a raw Markdown file as a GitHub-style page. ChatGPT file previews may not resolve adjacent assets. Keep the entire docs folder together rather than opening an isolated copy of wireframes.md.

[VS Code Markdown documentation](https://code.visualstudio.com/docs/languages/markdown)
