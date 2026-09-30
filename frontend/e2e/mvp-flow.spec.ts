// Phase 10: one browser pass through the page that Phases 5–9 already built.
// The test opens http://localhost:3000. It does not call port 8001.

// Assertions and the test handle.
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

// Local weight and SUN RGB-D path checks. They do not download.
import { photoSkipReason, relativeToRepo, sunTestPhotos } from "./photo-ready";

// Sentence that Phase 6 already parsed into budget, style, occupants, desk, and chair.
const sentence =
  "I want to redo my home office in a scandinavian style. I need a desk and a chair. The budget is 80000 rupees for 1 person.";

// Optional ceiling typed before the estimate. A rejected scale is retried without it.
const knownHeightM = "2.7";

// Facts printed as one line so the report can quote the run.
type FlowSummary = {
  // desktop or narrow.
  viewport: string;
  // Repo-relative JPEG, or null when the photo step did not run.
  photoPath: string | null;
  // True when the estimate panel was accepted.
  photoRan: boolean;
  // Skip reason, known-length note, or the found-objects line.
  photoNote: string;
  // Width before the correction.
  widthBefore: string;
  // Width after the correction.
  widthAfter: string;
  // Pareto points shown.
  points: number;
  // What the 3D caption showed for the design that was rendered.
  meshCaption: string;
  // generated, or the not-run note.
  image: string;
  // Advisory critic line.
  critic: string;
};

// Browser requests that must stay on this origin.
function watchForApiPort(page: Page): string[] {
  // URLs that escaped to the FastAPI port.
  const leaked: string[] = [];
  // Every request the page makes.
  page.on("request", (request) => {
    // The browser is not allowed to call port 8001.
    if (request.url().includes(":8001")) {
      // Record it for the assertion at the end.
      leaked.push(request.url());
    }
  });
  // The caller asserts this stays empty.
  return leaked;
}

// Mesh HTTP statuses for the design currently on screen.
function watchMeshes(page: Page): number[] {
  // Status codes from GET /api/meshes/{itemId}.
  const statuses: number[] = [];
  // Responses, including 404, which means the item stays a box.
  page.on("response", (response) => {
    // Only the mesh route.
    if (response.url().includes("/api/meshes/")) {
      // Remember the status.
      statuses.push(response.status());
    }
  });
  // The caller clears this array when the selected design changes.
  return statuses;
}

// True when the photo error is a missing file rather than a bad room.
function isMissingWeight(detail: string): boolean {
  // The worker names the exception. A missing floor is not one of these.
  return /MissingWeights|FileNotFoundError|requirements-train|\.venv-train/i.test(detail);
}

// True when the typed length cannot scale the photo. The retry drops the length.
function isScaleRejection(detail: string): boolean {
  // Messages from the photo route. They are not weight errors.
  return /times the photo estimate|no usable size|known_axis|known_length/i.test(detail);
}

// True when this JPEG had no floor. The next test-split file is tried.
function isNoFloor(detail: string): boolean {
  // The pipeline's readable reason.
  return /no floor was found/i.test(detail);
}

// Width the reviewer types. A short estimate is raised so a desk and chair can fit.
function reviewedWidth(current: string): string {
  // The field as a number.
  const numeric = Number(current);
  // Missing or very small estimates become a usable office width.
  if (!Number.isFinite(numeric) || numeric < 4.5) {
    // Metres. Two decimals match the photo fields.
    return "5.20";
  }
  // A visible correction of a tenth of a metre on an already usable width.
  return (Math.round((numeric + 0.1) * 100) / 100).toFixed(2);
}

// Raise a short length. A longer estimate is left as the photo measured it.
async function correctLengthIfShort(page: Page): Promise<void> {
  // Length field.
  const length = page.getByLabel("Room length (m)");
  // Current text.
  const numeric = Number(await length.inputValue());
  // Under 4 m is a tight room once the low-confidence inset is applied.
  if (!Number.isFinite(numeric) || numeric < 4) {
    // A length the Stage 1 office solves have already used.
    await length.fill("5.50");
  }
}

// Replace an implausible ceiling. A normal photo height is left alone.
async function correctHeightIfImplausible(page: Page): Promise<void> {
  // Height field.
  const height = page.getByLabel("Room height (m)");
  // Current text.
  const numeric = Number(await height.inputValue());
  // Crawlspace or a depth blow-up.
  if (!Number.isFinite(numeric) || numeric < 2.2 || numeric > 6) {
    // A typical indoor ceiling.
    await height.fill("2.80");
  }
}

// Widen any door the photo drew under the solver's 0.815 m limit.
async function correctNarrowDoors(page: Page): Promise<void> {
  // One type control per opening row.
  const types = page.getByLabel(/Opening \d+ type/);
  // Row count.
  const count = await types.count();
  // Each opening.
  for (let index = 0; index < count; index += 1) {
    // This row's type.
    const kind = await types.nth(index).inputValue();
    // Windows are not held to the door width.
    if (kind !== "door") {
      // Next row.
      continue;
    }
    // This row's width.
    const width = page.getByLabel(`Opening ${index + 1} width (m)`);
    // Metres.
    const metres = Number(await width.inputValue());
    // 0.90 m is above the 0.815 m hard limit.
    if (!Number.isFinite(metres) || metres < 0.9) {
      // Correct the opening before solving.
      await width.fill("0.90");
    }
  }
}

// Read the photo alert, if the estimate was rejected.
async function photoAlert(page: Page): Promise<string | null> {
  // The form's error paragraph inside the photo group.
  const alert = photoGroup(page).getByRole("alert");
  // No error.
  if (!(await alert.isVisible())) {
    // The estimate panel is the success path.
    return null;
  }
  // The reason the API returned.
  return (await alert.innerText()).trim();
}

// The photo fieldset. Next.js dev tools also expose an empty alert, so errors are read from this group only.
function photoGroup(page: Page): Locator {
  // The legend is the group's accessible name.
  return page.getByRole("group", { name: "Room from a photo (optional)" });
}

// Wait until the estimate panel or the photo error paragraph is on the page.
async function waitForEstimate(page: Page): Promise<"ready" | "alert"> {
  // Success copy.
  const ready = page.getByText("Check the numbers in Room below and correct them before solving.");
  // The photo form's error paragraph, not the dev-tools alert.
  const alert = photoGroup(page).getByRole("alert");
  // Either one ends the wait. The route allows five minutes.
  await expect(ready.or(alert)).toBeVisible({ timeout: 300_000 });
  // The panel wins when both could theoretically exist.
  if (await ready.isVisible()) {
    // Accepted estimate.
    return "ready";
  }
  // Rejected estimate.
  return "alert";
}

// Upload one JPEG and ask for an estimate. knownLength is omitted on the retry.
async function estimateOnce(page: Page, imagePath: string, knownLength: string | null): Promise<"ready" | "alert"> {
  // File input inside the Photo label.
  await page.getByLabel("Photo").setInputFiles(imagePath);
  // Known-length field.
  const known = page.getByLabel(/One known length in metres/);
  // Axis select.
  const axis = page.getByLabel(/That length is the room/);
  // A typed ceiling, or a blank field so the metric depth is used.
  if (knownLength === null) {
    // Clear a rejected length.
    await known.fill("");
  } else {
    // Metres.
    await known.fill(knownLength);
    // The value is the room height.
    await axis.selectOption("height");
  }
  // Start the perception worker.
  await page.getByRole("button", { name: "Estimate room from photo" }).click();
  // Wait until React has cleared the previous error. A leftover alert must not count as this attempt.
  await expect(page.getByRole("button", { name: "Estimating from photo..." })).toBeVisible({ timeout: 15_000 });
  // Panel or a new error. The route allows five minutes.
  return waitForEstimate(page);
}

// Run the photo step, or return a skip reason. Other failures throw.
async function runPhoto(page: Page): Promise<{ ran: boolean; note: string; imageRelative: string | null }> {
  // Missing weights or a missing image. The rest of the flow still runs.
  const skip = photoSkipReason();
  // Do not call the photo route when a weight file is absent.
  if (skip !== null) {
    // The caller records this sentence.
    return { ran: false, note: skip, imageRelative: null };
  }
  // Test-split JPEGs already exported. Nothing is downloaded.
  const photos = sunTestPhotos();
  // The export is not on this machine.
  if (photos.length === 0) {
    // Skip only the photo. The typed room still solves.
    return { ran: false, note: "photo skipped: SUN RGB-D test image is not on disk", imageRelative: null };
  }
  // Reasons from images that had no floor.
  const noFloor: string[] = [];
  // Try the preferred image, then another test image if that one has no floor.
  for (const imagePath of photos) {
    // Path printed in the report.
    const imageRelative = relativeToRepo(imagePath);
    // First try uses the optional known height.
    let outcome = await estimateOnce(page, imagePath, knownHeightM);
    // The API rejected the attempt.
    if (outcome === "alert") {
      // Text in the red paragraph.
      const detail = (await photoAlert(page)) ?? "photo estimate failed";
      // A missing weight skips the photo and keeps the typed room.
      if (isMissingWeight(detail)) {
        // Do not download a replacement.
        return { ran: false, note: `photo skipped: ${detail}`, imageRelative };
      }
      // The typed 2.7 m did not match this photo. Try the same file with metric depth.
      if (isScaleRejection(detail)) {
        // Second attempt.
        outcome = await estimateOnce(page, imagePath, null);
        // Still rejected.
        if (outcome === "alert") {
          // The second reason.
          const again = (await photoAlert(page)) ?? detail;
          // Weights disappeared between attempts.
          if (isMissingWeight(again)) {
            // Skip.
            return { ran: false, note: `photo skipped: ${again}`, imageRelative };
          }
          // A real failure. The weights are present, so the test stops.
          throw new Error(`photo estimate failed for ${imageRelative}: ${again}`);
        }
        // Metric depth was accepted after the typed height was rejected.
        const found = await page.getByText(/Found \d+ objects/).innerText();
        // Record both facts.
        return {
          // The panel is on the page.
          ran: true,
          // The known length was attempted and refused.
          note: `known height ${knownHeightM} m was rejected (${detail}); metric depth was used. ${found}`,
          // Which JPEG.
          imageRelative,
        };
      }
      // No floor in this JPEG. Try the next test-split file.
      if (isNoFloor(detail)) {
        // Remember it.
        noFloor.push(`${imageRelative}: ${detail}`);
        // Next image.
        continue;
      }
      // Any other rejection fails the photo step.
      throw new Error(`photo estimate failed for ${imageRelative}: ${detail}`);
    }
    // The estimate panel is visible.
    const found = await page.getByText(/Found \d+ objects/).innerText();
    // Known height was accepted.
    return {
      // Success.
      ran: true,
      // Scale sentence plus the object count.
      note: `known height ${knownHeightM} m. ${found}`,
      // Which JPEG.
      imageRelative,
    };
  }
  // Every candidate lacked a floor.
  throw new Error(`photo estimate failed: ${noFloor.join(" | ")}`);
}

// Fill the sentence and wait for the parser to copy the structured fields.
async function parseSentence(page: Page): Promise<void> {
  // The sentence box.
  await page.getByLabel("Room sentence").fill(sentence);
  // Parse does not solve.
  await page.getByRole("button", { name: "Parse sentence" }).click();
  // Success line, or the parser error inside the sentence group. Ollama can take the route's three minutes.
  const parsed = page.getByText("Parsed. The structured fields came from this sentence.");
  // The sentence fieldset. Its alert is the parser error, not the Next.js dev-tools alert.
  const alert = page.getByRole("group", { name: "Sentence" }).getByRole("alert");
  // Either result.
  await expect(parsed.or(alert)).toBeVisible({ timeout: 180_000 });
  // A failure is the test's failure. The fields must come from the sentence.
  if (!(await parsed.isVisible())) {
    // The reason.
    const detail = (await alert.isVisible() ? (await alert.innerText()).trim() : "the parser did not fill the form");
    // Stop.
    throw new Error(`parse failed: ${detail}`);
  }
  // Budget from the sentence.
  await expect(page.getByLabel("Budget (INR)")).toHaveValue("80000");
  // Style from the sentence. The sentence itself contains the word "style", so the label match must be the select.
  await expect(page.getByRole("combobox", { name: "Style", exact: true })).toHaveValue("scandinavian");
  // Occupants from the sentence.
  await expect(page.getByLabel("Occupant count")).toHaveValue("1");
  // Desk stays required. Exact so a longer category name cannot match.
  await expect(page.getByRole("checkbox", { name: "desk", exact: true })).toBeChecked();
  // Chair stays required. "armchair" also contains the letters chair.
  await expect(page.getByRole("checkbox", { name: "chair", exact: true })).toBeChecked();
  // The named solver constants are shown and were not edited.
  await expect(page.getByText(/Solver constants unchanged:/)).toBeVisible();
}

// Save the corrected room and read the Pareto heading, or throw the infeasible reason.
async function solve(page: Page): Promise<number> {
  // Submit.
  await page.getByRole("button", { name: "Save room and solve" }).click();
  // Feasible heading.
  const designs = page.getByRole("heading", { name: "Designs" });
  // Infeasible heading.
  const noDesign = page.getByRole("heading", { name: "No design" });
  // HTTP heading.
  const apiError = page.getByRole("heading", { name: "API error" });
  // The solve itself is milliseconds. The round trip still gets a minute.
  await expect(designs.or(noDesign).or(apiError)).toBeVisible({ timeout: 60_000 });
  // Infeasible text.
  if (await noDesign.isVisible()) {
    // The amber section.
    const reason = await page.locator("section").filter({ has: noDesign }).innerText();
    // The later panels need a design.
    throw new Error(reason);
  }
  // HTTP text.
  if (await apiError.isVisible()) {
    // The red section.
    const reason = await page.locator("section").filter({ has: apiError }).innerText();
    // Stop.
    throw new Error(reason);
  }
  // "N points" line.
  const summary = await page.getByText(/\d+ points,/).innerText();
  // The count.
  const match = /(\d+) points/.exec(summary);
  // The line is the one the assertion just saw.
  return Number(match?.[1] ?? "0");
}

// Click a different Pareto point when the set has one. False means the set had a single point.
async function selectAnotherPoint(page: Page): Promise<boolean> {
  // The button list under the chart. Each label contains a middot.
  const buttons = page.getByRole("button").filter({ hasText: "·" });
  // How many points are clickable.
  const count = await buttons.count();
  // A single point has nothing else to select.
  if (count < 2) {
    // Stay on the only design.
    return false;
  }
  // The design id currently drawn.
  const design = page.getByText(/^Design id:/);
  // Text before the click.
  const before = await design.innerText();
  // Prefer a point that is not already pressed.
  let target: Locator = buttons.nth(1);
  // Walk the list.
  for (let index = 0; index < count; index += 1) {
    // This button.
    const button = buttons.nth(index);
    // aria-pressed is the selected flag.
    const pressed = await button.getAttribute("aria-pressed");
    // The first unselected row.
    if (pressed !== "true") {
      // Use it.
      target = button;
      // Stop.
      break;
    }
  }
  // Select it. The plan, the bill, and the 3D view follow this id.
  await target.click();
  // The drawn id must change.
  await expect(design).not.toHaveText(before);
  // The caller checks captions for this new design.
  return true;
}

// 3D list for the design on screen.
function meshList(page: Page): Locator {
  // The section whose heading is the 3D view.
  return page.locator("section").filter({ has: page.getByRole("heading", { name: "3D view" }) }).locator("ul > li");
}

// Wait until mesh responses for this design have settled. A cached GLB adds no request.
async function waitForMeshResponses(page: Page, meshStatuses: number[], itemCount: number): Promise<void> {
  // Hard stop so a missing request cannot hold the GPU step.
  const deadline = Date.now() + 20_000;
  // If nothing arrives quickly, the GLB cache already has these items.
  const quietDeadline = Date.now() + 3_000;
  // How many responses had arrived at the last change.
  let last = meshStatuses.length;
  // When that count last changed.
  let lastChange = Date.now();
  // Poll the array the response listener fills.
  while (Date.now() < deadline) {
    // A new response arrived.
    if (meshStatuses.length !== last) {
      // Remember the new count.
      last = meshStatuses.length;
      // Reset the quiet timer.
      lastChange = Date.now();
    }
    // One response per placed object, and no straggler for a short moment.
    if (meshStatuses.length >= itemCount && Date.now() - lastChange >= 400) {
      // This design's lookups have finished.
      return;
    }
    // No request at all. The in-memory cache served the meshes.
    if (meshStatuses.length === 0 && Date.now() > quietDeadline) {
      // Captions still update from the cache.
      return;
    }
    // Some responses arrived and then stopped before the item count. Do not wait the full 20 s.
    if (meshStatuses.length > 0 && Date.now() - lastChange > 3_000) {
      // Use what arrived.
      return;
    }
    // Short pause. The fetch is started by the 3D view's effect.
    await page.waitForTimeout(200);
  }
}

// Wait until every caption is a box or a mesh, and a 200 response shows a mesh.
async function expectMeshOrBox(page: Page, meshStatuses: number[], waitForNetwork: boolean): Promise<string> {
  // The list is outside the canvas, so it is readable without WebGL pixels.
  const list = meshList(page);
  // At least one placed object.
  await expect.poll(async () => list.count(), { timeout: 20_000 }).toBeGreaterThan(0);
  // How many captions should have a mesh lookup.
  const itemCount = await list.count();
  // The first design always fetches. A later design may reuse the in-memory GLB cache.
  if (waitForNetwork) {
    // Do not use expect() for a wait that is allowed to time out.
    await waitForMeshResponses(page, meshStatuses, itemCount);
  }
  // A successful GLB must replace the box caption.
  if (meshStatuses.includes(200)) {
    // The caption updates after the file is parsed.
    await expect(page.getByText("Objaverse mesh").first()).toBeVisible({ timeout: 20_000 });
  }
  // Every line names one of the two kinds.
  const count = await list.count();
  // Captions.
  const captions: string[] = [];
  // Each object.
  for (let index = 0; index < count; index += 1) {
    // The line.
    const text = (await list.nth(index).innerText()).trim();
    // box or Objaverse mesh, and nothing else.
    expect(text).toMatch(/: (box|Objaverse mesh)$/);
    // Keep it for the summary.
    captions.push(text);
  }
  // One string for the report.
  return captions.join("; ");
}

// Render maps, then the image or the not-run note, then the critic line.
async function renderDesign(page: Page): Promise<{ image: string; critic: string }> {
  // The button is below the 3D view.
  await page.getByRole("button", { name: "Render this design" }).click();
  // Depth from the scene graph. Diffusion is allowed several minutes.
  const depth = page.getByRole("img", { name: "Depth map rendered from the scene graph" });
  // The route's own deadline is five minutes.
  await expect(depth).toBeVisible({ timeout: 320_000 });
  // Segmentation is returned with the depth map. It is not a second ControlNet.
  await expect(page.getByRole("img", { name: "Segmentation map rendered from the scene graph" })).toBeVisible();
  // Generated image, when the worker produced one.
  const generated = page.getByRole("img", { name: "Inpainted room" });
  // The section that holds the note and the maps.
  const panel = page.locator("section").filter({ has: page.getByRole("heading", { name: "Generated image" }) });
  // Image, or the existing not-run sentence. Photorealism is not checked.
  let image = "";
  // The figure is present only when image_status is generated.
  if (await generated.count()) {
    // The PNG is on the page.
    await expect(generated).toBeVisible();
    // Record that an image was returned. Do not judge the furniture it drew.
    image = "generated";
  } else {
    // The amber note is the API's image_note.
    const note = panel.locator("p").filter({ hasText: /diffusion|not run|not generated|weights|installed/i });
    // It must be non-empty.
    await expect(note.first()).toBeVisible();
    // The sentence itself.
    image = (await note.first().innerText()).trim();
  }
  // The result heading, not the introductory sentence above the button.
  const criticHeading = panel.getByText("Critic note", { exact: true });
  // The heading is the advisory note's label.
  await expect(criticHeading).toBeVisible();
  // The next paragraph is status plus note: "advisory. ..." or "not_run. ...".
  const criticLine = criticHeading.locator("xpath=following-sibling::p[1]");
  // That sentence.
  const critic = (await criticLine.innerText()).trim();
  // Either the VLM answered or the page says the critic did not run.
  expect(critic).toMatch(/^(advisory|not_run)\./);
  // The card.
  return { image, critic };
}

// Explanation sources, one what-if, and the version table.
async function explainAndCompare(page: Page): Promise<void> {
  // Ask for the trace-backed sentences.
  await page.getByRole("button", { name: "Explain this design" }).click();
  // Sources are the trace, not the model's invention. The route allows three minutes.
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible({ timeout: 180_000 });
  // Claims sit under the sources.
  await expect(page.getByRole("heading", { name: "Claims" })).toBeVisible();
  // At least one source sentence is on the page.
  const explanation = page.locator("section").filter({ has: page.getByRole("heading", { name: "Explanation" }) });
  // A fact from the trace.
  await expect(explanation.locator("li").first()).toBeVisible();
  // The budget field already holds 10% above the solved budget. Leave it.
  await page.getByRole("button", { name: "Run what-if" }).click();
  // Feasible summary. The proxy allows one minute.
  await expect(page.getByText(/Score change /).first()).toBeVisible({ timeout: 70_000 });
  // The plan switches to the what-if until the user goes back.
  await expect(page.getByText("Showing the what-if design. The Pareto set above is unchanged.")).toBeVisible();
  // Version history for the Pareto design the what-if started from.
  await page.getByRole("button", { name: "Compare versions" }).click();
  // Column from the version table.
  await expect(page.getByRole("columnheader", { name: "Version" })).toBeVisible({ timeout: 30_000 });
  // Version numbers are the first cell of each row. Version 2 is the what-if.
  await expect
    .poll(async () => {
      // First column.
      const texts = await page.locator("tbody tr td:first-child").allInnerTexts();
      // Trimmed version numbers.
      return texts.map((text) => text.trim());
    })
    .toContain("2");
}

// The document itself must not grow wider than the viewport. Inner tables may scroll.
async function expectNoPageOverflow(page: Page): Promise<void> {
  // scrollWidth minus clientWidth. A 1 px rounding gap is ignored.
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  // No sideways page scroll.
  expect(overflow).toBeLessThanOrEqual(1);
}

// The full MVP flow on whatever viewport the project set.
async function runFlow(page: Page, info: TestInfo): Promise<void> {
  // Port 8001 leaks.
  const leaked = watchForApiPort(page);
  // Mesh statuses. Cleared when a new design is selected so the caption matches that design.
  const meshStatuses = watchMeshes(page);
  // Open the page.
  await page.goto("/");
  // The health line is served by the Next.js proxy.
  await expect(page.getByText("API status: ok (HTTP 200)")).toBeVisible();
  // A fresh scene id so this run does not depend on an older version number.
  const sceneId = `e2e-${info.project.name}-${Date.now()}`;
  // Scene id field.
  await page.getByLabel("Scene id").fill(sceneId);
  // Photo, or a recorded skip.
  const photo = await runPhoto(page);
  // Width field. Exact name so an object width row is not edited by mistake.
  const width = page.getByRole("textbox", { name: "Room width (m)", exact: true });
  // The photo value, or the form default.
  const widthBefore = await width.inputValue();
  // A photo estimate can also need a longer floor or a wider door.
  if (photo.ran) {
    // The version line names the photo save.
    await expect(page.getByText(/photo estimate was saved/)).toBeVisible();
    // Short rooms are corrected before the width nudge.
    await correctLengthIfShort(page);
    // Implausible ceilings are corrected.
    await correctHeightIfImplausible(page);
    // Narrow doors are corrected.
    await correctNarrowDoors(page);
  }
  // The dimension this phase always changes.
  const widthAfter = reviewedWidth(widthBefore);
  // Type it. fill() updates the controlled input.
  await width.fill(widthAfter);
  // The field must show the correction before the sentence is parsed.
  await expect(width).toHaveValue(widthAfter);
  // Natural-language requirement. Parsing does not edit the room size.
  await parseSentence(page);
  // A later render must not have put the photo width back.
  if ((await width.inputValue()) !== widthAfter) {
    // Put the correction back before solving.
    await width.fill(widthAfter);
  }
  // The value that will be saved.
  await expect(width).toHaveValue(widthAfter);
  // Solve the corrected room.
  const points = await solve(page);
  // One to eight points.
  expect(points).toBeGreaterThanOrEqual(1);
  // The same upper bound the Pareto route already uses.
  expect(points).toBeLessThanOrEqual(8);
  // 2D plan for the first point.
  await expect(page.getByRole("heading", { name: "2D plan" })).toBeVisible();
  // The plan's accessible name includes the object count.
  await expect(page.getByRole("img", { name: /Top view of/ })).toBeVisible();
  // 3D heading.
  await expect(page.getByRole("heading", { name: "3D view" })).toBeVisible();
  // The canvas element is mounted. Pixel colours are not asserted.
  await expect(page.locator("canvas")).toBeVisible();
  // Captions for the first point, so a mesh fetch is observed before the selection changes.
  const firstCaption = await expectMeshOrBox(page, meshStatuses, true);
  // Drop statuses from the first point. A cached GLB may add none for the next point.
  meshStatuses.splice(0, meshStatuses.length);
  // Another Pareto point, when the set has one.
  const changedPoint = await selectAnotherPoint(page);
  // Captions for the design that the rest of the flow renders.
  const meshCaption = changedPoint ? await expectMeshOrBox(page, meshStatuses, true) : firstCaption;
  // Depth, segmentation, image or note, critic.
  const rendered = await renderDesign(page);
  // Bill of materials for the same design.
  await expect(page.getByRole("heading", { name: "Bill of materials" })).toBeVisible();
  // The catalog id column.
  await expect(page.getByRole("columnheader", { name: "item_id" })).toBeVisible();
  // At least one catalog row.
  await expect(page.getByRole("cell", { name: /^cat_/ }).first()).toBeVisible();
  // The total row.
  await expect(page.getByRole("cell", { name: /₹/ }).first()).toBeVisible();
  // A mismatch between the lines and design.cost would be this sentence.
  await expect(page.getByText(/Line totals sum to/)).toHaveCount(0);
  // Explanation, what-if, versions.
  await explainAndCompare(page);
  // No horizontal page scroll at this viewport.
  await expectNoPageOverflow(page);
  // The browser stayed on port 3000.
  expect(leaked).toEqual([]);
  // One machine-readable line for the phase report.
  const summary: FlowSummary = {
    // Project name.
    viewport: info.project.name,
    // JPEG, if the photo ran.
    photoPath: photo.imageRelative,
    // Whether the estimate panel was used.
    photoRan: photo.ran,
    // Skip or success note.
    photoNote: photo.note,
    // Width before.
    widthBefore,
    // Width after.
    widthAfter,
    // Point count.
    points,
    // Caption lines.
    meshCaption,
    // Image or not-run note.
    image: rendered.image,
    // Critic card.
    critic: rendered.critic,
  };
  // stdout, picked up by the list reporter.
  console.log(`PHASE10 ${JSON.stringify(summary)}`);
  // The HTML report keeps the same facts.
  info.annotations.push({ type: "phase10", description: JSON.stringify(summary) });
}

// Desktop, then the narrow project. Each one is a full pass.
test("full MVP flow", async ({ page }, info) => {
  // Photo, sentence, solve, plan, 3D, render, bill, explanation, what-if, versions.
  await runFlow(page, info);
});
