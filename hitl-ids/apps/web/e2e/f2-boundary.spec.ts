import { expect, test } from "@playwright/test";

test("V3 strict informational boundary: positives, reviewer examples, unfamiliar vocabulary and known attacks", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("g.ang");
  await page.getByLabel("Password", { exact: true }).fill("analyst-demo");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/analyst\/operations$/);
  const detail=page.getByRole("region",{name:"Operational alert workspace"});
  async function select(title:string) {
    await page.getByLabel("Search operational alerts",{exact:true}).fill(title);
    const row=page.getByRole("list",{name:"Operational alerts"}).getByRole("button").first();
    await expect(row).toContainText(title);await row.click();
    await expect(detail.getByRole("heading",{name:title,exact:true})).toBeVisible();
  }
  await select("Informational notice: software version");
  await expect(detail).toContainText("Classification: Informational / Policy Signal");
  await expect(detail).toContainText("Routine Review");
  await expect(detail.getByRole("link",{name:"Open Tier 2 Case",exact:true})).toHaveCount(0);
  for(const title of ["ET POLICY Possible ransomware communication","ET POLICY Credential harvesting detected",
    "ET POLICY Unauthorized remote access detected","ET POLICY Opaque channel rendezvous"]) {
    await select(title);
    await expect(detail).toContainText("Unknown / Needs Expert");
    await expect(detail).toContainText("Expert Review Required");
    await expect(detail).not.toContainText("Informational / Policy Signal");
    await expect(detail.getByRole("link",{name:"Open Tier 2 Case",exact:true})).toBeVisible();
    await expect(detail.getByRole("button",{name:"Approve Tier 2",exact:true})).toHaveCount(0);
  }
  await select("ET POLICY SQL injection");
  await expect(detail).toContainText("web attack");
  await expect(detail).toContainText("Routine Review");
});
