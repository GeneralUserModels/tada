# Tabracadabra 🎉

> [!WARNING]
> Heads up- this project is a massive hack that relies on PyObjC and keyboard event tapping (capturing system-wide keystrokes and injecting synthetic text) plus a bunch of other things. It's definitely a proof of concept and will probably break often. Also only works on Macs!

## What is this?

Tabracadabra 🎉 is a system-wide AI autocomplete that lets you summon intelligent text completion anywhere on your Mac by holding the Tab key. Think of it as GitHub Copilot, but for literally any text field - emails, messages, documents, terminal, you name it.

## How it works

1. **Hold Tab** - Activates the system and takes a screenshot of your current screen
2. **Loading Spinner** - Shows a spinner while the system processes your request
3. **Use GUM** - Uses the General User Model to retrieve context from the user
4. **Completions** - Streams helpful text completions directly into whatever app you're using
5. **Release Tab** - Commits the suggestion and keeps it, or cancels if no content started
6. **Quick Tab Tap** - Just inserts a normal Tab character (passthrough behavior)

## Setup

0. Install and setup the General User Model. See the instructions at [https://generalusermodels.github.io/gum/](https://generalusermodels.github.io/gum/).

1. Set up your environment:
   ```bash
   cp .env.example .env
   # Add your OPENAI_API_KEY and USER_NAME
   ```

2. **Important**: Give the Terminal permissions in System Preferences → Security & Privacy → Accessibility

3. Run it:
   ```bash
   uv run python main.py
   ```

## Why this exists

Sometimes you just want AI autocomplete everywhere, not just in your code editor.