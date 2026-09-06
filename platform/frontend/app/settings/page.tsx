"use client";

/** One place for everything a clinician configures (SPEC-019).
 *
 * `/profile` and `/preferences` were two top-level destinations for what is,
 * from the outside, one thing: settings. Both are still their own component —
 * the merge is in the navigation, not in the code — and the section lives in
 * the URL so a link can point straight at automation preferences.
 */

import { useRouter, useSearchParams } from "next/navigation";
import { useLanguage } from "@/lib/language";
import SegmentedControl from "@/components/ui/segmented-control";
import ProfileSection from "@/components/settings/profile-section";
import AutomationSection from "@/components/settings/automation-section";

type Section = "profile" | "automation";

export default function SettingsPage() {
  const { t } = useLanguage();
  const router = useRouter();
  const params = useSearchParams();
  const section = (params.get("section") as Section) || "profile";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-extrabold">{t("settings.title")}</h1>
        <p className="text-sm text-muted">{t("settings.subtitle")}</p>
      </div>

      <SegmentedControl<Section>
        label={t("settings.sections")}
        value={section}
        onChange={(next) => router.replace(`/settings?section=${next}`, { scroll: false })}
        options={[
          { value: "profile", label: t("settings.section.profile") },
          { value: "automation", label: t("settings.section.automation") },
        ]}
      />

      {section === "profile" ? <ProfileSection /> : <AutomationSection />}
    </div>
  );
}
