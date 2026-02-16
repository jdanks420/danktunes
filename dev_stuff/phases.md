# Danktunes Improvement Plan

This document outlines a phased approach to improving danktunes' stability, maintainability, and features.

---

## Phase 1: Code Cleanup & Foundation (1-2 weeks)

### Goals
- Clean up the codebase, remove dead code, and establish consistent patterns
- Fix integration issues between existing modular components

### Tasks

#### 1.1 Consolidate State Management
- [x] Choose ONE state management approach (main file `state` object vs `src/state.py`)
- [x] Remove duplicate `validate_state()` functions
- [x] Decide: either fully use `src/state.py` or remove it entirely

#### 1.2 Remove Dead Code & Unused Imports
- [x] Audit and remove unused functions in main file
- [x] Clean up duplicate playlist functions (e.g., `save_playlist` wrapping `save_playlist_m3u`)
- [x] Remove unused `src/` modules if not integrated, or integrate them properly

#### 1.3 Fix Known Issues
- [x] Fix duplicate code in `toggle_pause()` (lines 921-938 have repeated logic)
- [ ] Fix overlay state conflicts more robustly
- [ ] Handle edge cases in `scan_directory()` (permission errors, symlinks)

#### 1.4 Code Style
- [x] Add consistent docstrings to all public functions
- [x] Add type hints where missing
- [ ] Set up pre-commit hooks for linting

---

## Phase 2: Testing & Reliability (2-3 weeks)

### Goals
- Establish test coverage for critical functionality
- Improve error handling and edge cases

### Tasks

#### 2.1 Testing Infrastructure
- [x] Set up pytest framework
- [x] Add tests for:
  - [x] `scan_directory()` - various directory structures
  - [x] Playlist functions (add, remove, save, load)
  - [x] M3U import/export
  - [x] State validation
  - [ ] Search functionality

#### 2.2 Error Handling Improvements
- [ ] Wrap `subprocess` calls in proper try/except blocks
- [ ] Add fallback handling when external tools (mpg123, ffprobe) are missing
- [ ] Handle corrupt audio files gracefully
- [ ] Handle filesystem permission errors

#### 2.3 Edge Cases
- [ ] Empty music directory
- [ ] Non-ASCII filenames (Unicode)
- [ ] Very long file paths
- [ ] Directory with thousands of files (performance)
- [ ] Network-mounted directories

---

## Phase 3: Architecture & Refactoring (2-3 weeks)

### Goals
- Improve code organization and maintainability
- Reduce code duplication

### Tasks

#### 3.1 Modularization (Choose One Path)

**Option A: Fully Modular** (if src/ modules should be used)
- [ ] Integrate `src/config.py` properly with TOML support
- [ ] Integrate `src/audio.py` for player abstraction
- [ ] Use `src/state.py` as the single source of truth
- [ ] Refactor main.py to use imported modules

**Option B: Keep Monolithic** (simpler, faster)
- [x] Remove src/ directory entirely
- [x] Organize main file with clear section markers
- [x] Create internal submodules within danktunes.py

#### 3.2 Reduce Code Duplication
- [x] Consolidate playlist scroll offset calculations
- [x] Merge duplicate navigation handlers (arrows, j/k)
- [x] Unify overlay drawing logic

---

## Phase 4: Feature Stability (Ongoing)

### Goals
- Fix bugs and improve existing features

### Tasks

#### 4.1 Playback Reliability
- [ ] Fix pause/resume for aplay (currently restarts from saved position, not true resume)
- [ ] Improve seeking accuracy
- [ ] Handle track change during seek

#### 4.2 UI/UX Improvements
- [x] Fix terminal resize edge cases
- [x] Handle very small terminal sizes gracefully
- [ ] Improve help overlay scrolling for many shortcuts

#### 4.3 Configuration Persistence
- [x] Save/restore volume level
- [x] Save last played track and position
- [x] Remember expanded directories

---

## Phase 5: New Features (Future)

### Tasks (From TODO.md)
- [x] Last position memory for podcasts/audiobooks
- [ ] Queue system (separate from playlist)
- [x] Sort options (name, date, duration, play count)
- [x] Favorites/bookmarks system
- [x] Smart shuffle (prevent recent repeats)
- [ ] Gapless playback
- [ ] Sleep timer

### Advanced Features (Lower Priority)
- [ ] Remote control (MPRIS support)
- [ ] Network streaming
- [ ] Mini mode (compact display)

---

## Phase 6: Performance & Optimization (As Needed)

### Tasks
- [x] Profile duration scanning (currently synchronous, blocks startup)
- [x] Add async/caching for metadata fetching
- [x] Optimize flat_tree() for large directories
- [x] Consider caching expanded directory contents

---

## Phase 7: Polish & Release (1 week)

### Tasks
- [ ] Add comprehensive error messages
- [ ] Improve documentation (README is already good)
- [x] Set up CI/CD (GitHub Actions)
- [x] Add version number and --version flag
- [x] Create proper release process

---

## Summary

| Phase | Focus | Estimated Time |
|-------|-------|----------------|
| 1 | Code Cleanup | 1-2 weeks |
| 2 | Testing | 2-3 weeks |
| 3 | Architecture | 2-3 weeks |
| 4 | Stability | Ongoing |
| 5 | New Features | Future |
| 6 | Performance | As needed |
| 7 | Polish | 1 week |

**Priority Recommendation:** Start with Phase 1 to establish a clean foundation before adding tests or new features. The most impactful quick wins are:
1. Fixing the duplicate state validation
2. Removing unused code
3. Consolidating the configuration approach
