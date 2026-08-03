# Windows acceptance workflow — canvas-first editor round 3

This round uses the deterministic three-stage editor:

1. Import a badge image and generate the initial region.
2. In **区域**, use left-button tools for add, erase, fill, rectangle and polygon edits. Use right-button drag for canvas pan at 100%, 200%, 400% and 800%.
3. Use ordinary wheel for zoom and Shift + wheel for the read-only brush size shown in the top status bar.
4. Confirm the region, click **生成高度图**, and verify that the default canvas is a true grayscale image: black is low, white is high, and outside the mask is zero.
5. Exercise set-height, raise, lower and smooth. Verify every edit is visible immediately and remains inside the approved region.
6. Confirm the height, export the 16-bit PNG, 8-bit preview PNG and optional 32-bit TIFF, then verify the displayed paths and file contents.
7. Save, close and reopen the project. Confirm the masks, grayscale master, brush sizes and approval states are restored before testing OBJ, STL and GLB.

Record the following evidence for the Draft PR:

- full-window screenshots at 125% or 150% DPI;
- a short right-drag pan recording;
- brush status before and after Shift + wheel;
- erase before/after comparison;
- pure grayscale height view;
- exported height files and their paths;
- the expanded **详细信息** log view.

The bottom bar remains a single concise user status. Technical task data and
formatted JSON belong only in **详细信息**, where entries are timestamped,
complete and capped at 200 records.
