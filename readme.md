# Personal Gesture Manager

* Author: Peem Narkkhwan
* Contact: sharetoyouaccess@gmail.com
* Version: 2026.11.09
* Compatible with: NVDA 2026.1 and later (last tested with NVDA 2026.3)

## 1. Introduction

Personal Gesture Manager brings together, in a single window, the commands and gestures of NVDA and of every installed add-on. In this guide, as in NVDA, the word "gesture" covers keyboard shortcuts, braille display keys and touch gestures.

With this add-on, you can:

* see every command of each add-on, together with its gestures;
* find gestures that are assigned to more than one command, and resolve them;
* add, change, remove or reset gestures, with an automatic backup before every change;
* see which commands you use, and which gestures you never use;
* test any gesture to find out what it does before you assign it;
* read a quick guide for any installed add-on, or open its full documentation and NVDA's own guides.

The information always reflects your own NVDA, whether installed or portable.

## 2. Getting Started

### Opening the Add-on

Press NVDA+G, or open the NVDA menu and select Tools, then Personal Gesture Manager.

### Resolving a Conflict

1. Press Ctrl+Tab to go to the Conflicts tab, then press Tab to reach the list.
2. Press Enter on a gesture, choose one of the commands that share it, and then choose either to change its gesture or to remove the gesture from it.
3. NVDA announces the result and the number of conflicts remaining. Continue with the next item.

### Assigning a Gesture to a Command

1. In the Commands by add-on tab, set Filter type (Alt+F) to "Commands without a gesture", press Tab to reach the list, and type the first letters of the command name.
2. Press Enter on the command and choose "Add a gesture".
3. Press the new gesture. NVDA tells you whether it is free or already in use, and then asks where it should apply.

### Changing or Removing a Gesture

Press Enter on a command. In the window that opens, press Enter on a gesture to change it, or Delete to remove it.

### Undoing a Change

Press Alt+B (Backups), select "Undo the last change", and answer Yes.

### Finding Gestures You Do Not Use

In the Statistics tab, set Filter type to "Unused commands with a gesture" and Period to "Last 30 days" or "All time". Usage is recorded from the day the add-on is installed, so it is best to wait a few weeks before drawing conclusions.

## 3. Using the Window

### Opening and Closing

You can open the add-on in either of these ways:

* Press NVDA+G. Like any other gesture, this one can be changed: in the Commands by add-on tab, select "Opens Personal Gesture Manager".
* From the NVDA menu, select Tools, then Personal Gesture Manager.

The command "Opens the gesture tester of Personal Gesture Manager" opens the Gesture tester tab directly. It has no gesture by default; you may assign one.

If the window is already open, NVDA+G brings it back to the front at the place you left, and NVDA says "Personal Gesture Manager is already open".

Press Escape, or Alt+C, to close the window.

### Tabs

The window has five tabs:

1. Commands by add-on
2. Conflicts
3. Statistics
4. Gesture tester
5. Guides for NVDA and add-ons

Press Ctrl+Tab or Ctrl+Shift+Tab to move to the next or previous tab, or Ctrl+1 to Ctrl+5 to go to a tab directly. NVDA announces the name of the tab, followed by its first control.

When you arrive at the Conflicts tab, NVDA tells you how many gestures involving add-ons are shared, by type: conflicts first, then overrides and those that depend on focus, for example "3 conflicts between add-ons, 2 overrides, 1 depends on focus". Types with none are left out, and nothing is announced when no gesture is shared.

### Keyboard Shortcuts in the Window

The following Alt keys work in both English and Thai. NVDA announces them for each control, except for lists.

* All tabs: Alt+C Close.
* Commands by add-on: Alt+A Add-on, Alt+F Filter type, Alt+O Commands, Alt+S Adjust gestures for this command, Alt+B Backups.
* Conflicts: Alt+F Filter type, Alt+I Include overlaps between NVDA's own commands, Alt+S Shared gestures.
* Statistics: Alt+P Period, Alt+A Add-on, Alt+F Filter type, Alt+U Commands by use, Alt+M Summary, Alt+D Delete all statistics.
* Gesture tester: Alt+S Start testing gestures, Alt+R Test results.
* Guides for NVDA and add-ons: Alt+A Add-ons and NVDA, Alt+Q Quick guide, Alt+G Open full guide.

In lists:

* Type the first letters of a name to move to it.
* Press Enter, or the Applications key (Shift+F10), to see what you can do with the selected item.
* In the Commands and Conflicts lists, press Delete to remove a gesture.
* When a list is empty, NVDA tells you why, for example "No conflicts".

Press F1 anywhere in the window to open this guide at the section for the current tab.

### Interface Language

The window appears in NVDA's language when a translation is available, and in English otherwise. Press Ctrl+T to switch between Thai and English. NVDA announces the change in both languages, so you can always switch back, and your position in the window is kept. Your choice is remembered after NVDA restarts.

Command names and gesture names are provided by NVDA, so they always appear in NVDA's language.

### Information About Your System

Press NVDA+T in the window to hear a short summary: the NVDA version, whether it is installed or portable, the computer name and the Windows version.

* Press NVDA+T twice quickly to hear full details, one per line: the NVDA version and folder, where your gestures and settings are saved, the keyboard layout and input language, the number of conflicts and installed add-ons, the Windows edition and build, and the application whose commands are shown.
* Press NVDA+T three times quickly to copy these details to the clipboard, for example to include them in a request for help. The details contain your computer name and Windows user name, so please review them before sharing them publicly.

Outside this window, NVDA+T works as usual.

## 4. Commands by Add-on Tab {#commands}

Use this tab to review and change gestures.

### 4.1 Choosing What to Show

* Add-on: choose whose commands to show.
    * All add-ons (default): the commands of all add-ons, without NVDA's own commands.
    * NVDA: NVDA's own commands only.
    * The name of an add-on: the commands of that add-on only.
    * All add-ons and NVDA: every command.
* Filter type: choose which commands to show.
    * Commands with a gesture (default): the commands you can already run with a gesture.
    * Commands with more than one gesture: useful for checking whether every gesture is still needed.
    * Commands without a gesture: commands to which you can assign a gesture.
    * All commands.

### 4.2 Reading the List

Each row gives the command name and its gestures. Commands without a gesture show "No gesture". If one of its gestures is also used by another command, the row also says "Gesture conflict". When all add-ons are shown, each row ends with the name of the add-on.

### 4.3 Adjusting the Gestures of a Command

Press Enter on a command, or choose "Adjust gestures for this command" (Alt+S). A window opens with:

* Gestures: the list of the command's gestures. Press Enter on a gesture to change it, or Delete to remove it.
* Add a gesture
* Reset this command to default
* Reset all commands of the add-on to default
* Close

### 4.4 Adding or Changing a Gesture

"Add a gesture" adds another gesture while keeping the existing ones. To replace a gesture, press Enter on it in the Gestures list instead.

1. Press the new gesture.
2. If it is a key normally used for typing, such as a letter, a digit, Space, Enter or an arrow key, NVDA asks you to confirm, because that key would no longer type. Answer No to press a different key instead.
3. NVDA tells you whether the gesture is free or which command already uses it.
4. For a keyboard gesture, choose where it applies: all keyboard layouts, desktop layout only or laptop layout only.
5. If another command already uses the gesture, choose one of the following:
    * Move it to this command: the gesture is taken from the other command and given to this one.
    * Keep on both commands: both commands keep the gesture. NVDA tells you which one will actually run.
    * Choose another gesture: press a different gesture.
    * Cancel: nothing is changed.

    An extra warning is given if the other command belongs to NVDA itself.

When you replace a gesture, the old one is removed only after the new one has been confirmed to work. If a change cannot be applied, NVDA tells you and nothing is left half done.

### 4.5 Removing a Gesture

Select a command and press Delete. If the command has more than one gesture, choose the one to remove. You are asked to confirm before anything is removed.

### 4.6 Restoring Default Gestures

From the window opened with Enter on a command:

* Reset this command to default: removes all your changes to this command. NVDA then tells you its current gestures.
* Reset all commands of the add-on to default: removes all your changes to every command of the same add-on, or of NVDA. You are asked to confirm first.

### 4.7 Backups and Undo

A backup of your gestures is made automatically before every change. The ten most recent backups are kept.

Choose Backups (Alt+B) to see them:

* "Undo the last change" is always first and tells you which change it undoes.
* The other items show the date and time and the change that followed, for example "2026-10-03 14:22:05, before adding NVDA+Shift+X to Say time".

Restoring a backup replaces all of your custom gestures, including those changed in NVDA's own Input gestures dialog. Your current gestures are backed up first, so a restore can also be undone.

## 5. Conflicts Tab {#conflicts}

This tab lists gestures that are assigned to more than one command.

Filter type:

* Conflict (default): only one of the commands can run, and it is not possible to know which one. These should be resolved.
* Override: one command always takes priority. The command marked "(runs now)" is the one that runs.
* Depends on focus: which command runs depends on where you are, for example in a document or in an edit field.

By default, only gestures involving add-ons are listed. Check "Include overlaps between NVDA's own commands" to include those between NVDA's own commands as well.

Each row shows the gesture, its keyboard layout and the number of commands that share it, for example "NVDA+F12, all keyboard layouts, 2 commands".

Press Enter on a row and choose one of the commands that share the gesture. Then choose:

* Change the gesture of this command: press a new gesture straight away.
* Remove the gesture from this command. If only two commands share it, the other command keeps it.
* Only this command uses the gesture: available when three or more commands share it. The gesture is removed from all the others.

Press Delete on a row to remove the gesture from the command you choose.

After each change, you stay in the list, and NVDA announces the result and the number of conflicts remaining.

## 6. Statistics Tab {#statistics}

This tab shows which commands you use and how often.

* Period: This NVDA session, Today, Last 7 days, Last 30 days or All time.
* Add-on: the same choices as in the Commands by add-on tab.
* Filter type:
    * Most used commands: these commands deserve gestures that are easy to press.
    * Least used commands: commands with a gesture that were used in the period, least used first.
    * Unused commands with a gesture: their gestures could be given to other commands.
* Commands by use: each row gives the command, the number of uses, its gestures and its add-on. Press Enter on a row to go to the command in the Commands by add-on tab.
* Summary: the period, the totals and the date on which recording started.
* Delete all statistics: deletes all recorded usage and starts again. You are asked to confirm first.

By default, the tab shows the last 7 days for all add-ons, most used first. Your choices are remembered.

Each press of a gesture counts as one use.

## 7. Gesture Tester Tab {#tester}

1. Choose "Start testing gestures".
2. Press any key or perform any gesture. NVDA tells you whether the gesture is free, or which command and add-on use it. The command itself is not run.
3. Continue with other gestures to test them one after another.
4. Press Escape to stop. On a braille display or touch screen, perform the same gesture twice in a row to stop. Testing also stops when you switch to another window.

"Test results" lists every result, newest first, until NVDA is restarted. You can read the list with the arrow keys, or select and copy it.

The results apply to the application you were using before opening the add-on.

## 8. Guides for NVDA and Add-ons Tab {#guides}

This tab helps you learn how to use NVDA and each installed add-on.

1. Add-ons and NVDA: the NVDA User Guide and the Commands Quick Reference are listed first, followed by every installed add-on with its status (Running, Not running or Disabled) and a short description.
2. Press Enter on an add-on, or choose Quick guide (Alt+Q), to read a short guide containing:
    * what the add-on does, as described by its developer;
    * all of its commands, grouped by category, with their gestures;
    * any gestures it shares with other commands;
    * its version, author and status.
3. To read the developer's full documentation, choose Open full guide (Alt+G). If the guide is available in more than one language, you are asked which one to open.
4. Press Enter on an NVDA entry to open that guide directly.

The quick guide opens in NVDA's message window. Read it with the arrow keys, and press H to move between headings. Commands are shown only for add-ons that are running.

## 9. Privacy and Your Data

* The add-on records only how many times each command is used. It never records what you type.
* Statistics, settings and backups are stored in a "personalGestureManager" folder inside NVDA's configuration folder.
* When you remove the add-on, this folder is deleted after NVDA restarts. Your gestures are not affected, because NVDA keeps them in its own settings. When you update the add-on, your data is kept.

## 10. Limitations

* Commands that apply to a single application are shown only for the application you were using before opening the add-on.
* The Escape key cannot be tested, because it is used to stop testing.
* The add-on cannot be used on secure screens, such as the Windows sign-in screen.
* Some commands of the same add-on cannot share a key. In that case, giving the key to another command always moves it, and NVDA tells you so before you confirm.
