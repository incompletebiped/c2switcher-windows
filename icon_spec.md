# C2Switcher Tray Icon — Design Specification

Reference SVG: `assets/icon-spec.svg`

\---

## Concept

The icon represents three stacked Claude Code accounts. At a glance it communicates:

* How many accounts exist
* Which account is currently active
* The worst usage state across all accounts

\---

## Visual Structure

```
┌─────────────────────────────────────┐
│  \\\[●] ████████████████  (inactive)   │  ← row 1
├─────────────────────────────────────┤
│  \\\[●] ████████████████ ▌ (active)    │  ← row 2  brightest fill + right tick
├─────────────────────────────────────┤
│  \\\[●] ████████████     (inactive)    │  ← row 3  darkest fill
│                               (◉)   │  ← status dot, bottom-right corner
└─────────────────────────────────────┘
```

\---

## Color Palette

### Background

|Element|Hex|Usage|
|-|-|-|
|Icon bg|`#26215C`|Outer rounded square|
|Halo ring|`#26215C`|Dark ring behind status dot|

### Account rows

|State|Hex|Usage|
|-|-|-|
|Active row|`#7F77DD`|Currently active account|
|Inactive row|`#534AB7`|Standard inactive accounts|
|Dim row|`#3C3489`|Third / least prominent account|

### Row foreground

|Element|Hex|Usage|
|-|-|-|
|Avatar circle|`#EEEDFE`|Used in both active and inactive|
|Active text bar|`#EEEDFE`|Primary label bar in active row|
|Inactive text|`#AFA9EC`|Primary label bar in inactive rows|
|Active tick|`#EEEDFE`|Vertical right-edge tick, 45% opacity|
|Secondary bar|`#EEEDFE`|Sub-label bar, 45% opacity (active)|

### Status dot

|State|Outer ring|Inner fill|
|-|-|-|
|Ok|`#3B6D11`|`#639922`|
|Warning|`#854F0B`|`#BA7517`|
|Limit|`#791F1F`|`#E24B4A`|

The dot has a dark halo (`#26215C`) so it is readable on any taskbar background color,
including light, dark, and custom Windows themes.

\---

## Active Account Row

Only one row is active at a time. The active row:

* Uses `#7F77DD` fill (brighter than inactive rows)
* Has a small vertical tick on the right inner edge (`6px wide`, `40% height`, `#EEEDFE` at 45% opacity)
* Uses `#EEEDFE` (bright white-purple) for all foreground text/bar elements

Inactive rows use `#534AB7` or `#3C3489` fill and `#AFA9EC` foreground elements.

The account order in the icon is fixed top-to-bottom and matches the account index order
in the database (index 0 = top row, index 2 = bottom row).

\---

## Status Dot Logic

The status dot reflects the **worst state across all accounts**, not just the active one.

Priority order (worst wins):

1. `Limit` — any account at ≥ 90% five-hour or seven-day usage
2. `Warning` — any account at ≥ 70% on either metric
3. `Ok` — all accounts below 70%

The dot sits in the **bottom-right corner** of the icon with a dark halo ring so it is
always readable regardless of taskbar background.

\---

## Required ICO Sizes

When exporting to `.ico`, generate layers at all of the following:

|Size|Corner radius (approx)|
|-|-|
|256px|`rx=56`|
|64px|`rx=14`|
|48px|`rx=10`|
|32px|`rx=7`|
|16px|`rx=3`|

At 16px the row detail is minimal — three flat bars of different shades plus the status
dot is sufficient. Do not try to render the avatar circle or tick at 16px.

\---

## Runtime Rendering (C# / GDI+)

The `.ico` embedded in the assembly is the **static base icon** (account 2 active, status ok).

At runtime, the tray icon should be **redrawn dynamically** using `System.Drawing` / GDI+
whenever account state changes, rather than swapping static `.ico` files.

### What changes at runtime

* Which row is highlighted (active account index)
* Status dot color (worst state across accounts)

### Recommended approach

```csharp
private Icon RenderTrayIcon(int activeAccountIndex, UsageStatus worstStatus)
{
    using var bmp = new Bitmap(32, 32);
    using var g = Graphics.FromImage(bmp);
    g.SmoothingMode = SmoothingMode.AntiAlias;

    // Background
    FillRoundedRect(g, new SolidBrush(Color.FromArgb(0x26, 0x21, 0x5C)),
        new Rectangle(0, 0, 32, 32), 7);

    // Draw three rows — highlight the active one
    for (int i = 0; i < 3; i++)
    {
        bool isActive = (i == activeAccountIndex);
        Color rowColor = i == 0 \\\&\\\& !isActive ? Color.FromArgb(0x53, 0x4A, 0xB7)
                       : i == 2 \\\&\\\& !isActive ? Color.FromArgb(0x3C, 0x34, 0x89)
                       : isActive            ? Color.FromArgb(0x7F, 0x77, 0xDD)
                                             : Color.FromArgb(0x53, 0x4A, 0xB7);
        // ... draw row rect, avatar dot, label bars
        // ... if isActive, draw right-edge tick
    }

    // Status dot with halo
    Color dotColor = worstStatus switch
    {
        UsageStatus.Limit   => Color.FromArgb(0xE2, 0x4B, 0x4A),
        UsageStatus.Warning => Color.FromArgb(0xBA, 0x75, 0x17),
        \\\_                   => Color.FromArgb(0x63, 0x99, 0x22)
    };
    // Draw halo then dot at bottom-right corner

    return Icon.FromHandle(bmp.GetHicon());
}
```

The `NotifyIcon.Icon` property is updated by calling `RenderTrayIcon()` on a timer
(suggested: every 60 seconds, matching the original c2switcher poll interval) or
immediately on any account switch event.

\---

## What NOT to do

* Do not use three separate static `.ico` files for status states — GDI+ runtime rendering
handles this in one place with no file management overhead
* Do not render the avatar circle or label bars at 16px — too much detail, use three
flat color bars only
* Do not skip the dark halo on the status dot — it will disappear on light taskbars

