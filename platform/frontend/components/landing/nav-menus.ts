/** What the landing header's menus contain. Each menu opens a panel of destinations
 * with a line saying what is behind each one; the header used to hold four bare
 * anchors to sections of the same page, which told a visitor nothing and went nowhere
 * a scroll would not. The page's own sections stay in the first menu, explained, and
 * the others lead out of the page: to the patient portal and to the project. */
export interface NavItem {
  href: string;
  titleKey: string;
  bodyKey: string;
  /** Opens another site: shown with an icon and in a new tab. */
  external?: boolean;
  /** The id of the page section this item jumps to, for the scroll-spy. */
  section?: string;
}

export interface NavMenu {
  id: string;
  labelKey: string;
  eyebrowKey: string;
  items: NavItem[];
  /** A highlighted shortcut shown above the items, like the notice strip in Hermes'. */
  promo?: NavItem;
}

const REPO = "https://github.com/Juanpacol/SEPHIROTH";

export const NAV_MENUS: NavMenu[] = [
  {
    id: "product",
    labelKey: "marketing.nav.product",
    eyebrowKey: "marketing.nav.product.eyebrow",
    items: [
      {
        href: "#features",
        titleKey: "marketing.nav.features.title",
        bodyKey: "marketing.nav.features.body",
        section: "features",
      },
      {
        href: "#how-it-works",
        titleKey: "marketing.nav.howItWorks",
        bodyKey: "marketing.nav.howItWorks.body",
        section: "how-it-works",
      },
      { href: "#faq", titleKey: "marketing.nav.faq", bodyKey: "marketing.nav.faq.body", section: "faq" },
    ],
  },
  {
    id: "patients",
    labelKey: "marketing.nav.patients",
    eyebrowKey: "marketing.nav.patients.eyebrow",
    items: [
      { href: "/portal/claim", titleKey: "marketing.nav.claim.title", bodyKey: "marketing.nav.claim.body" },
      {
        href: "/login",
        titleKey: "marketing.nav.patientSignIn.title",
        bodyKey: "marketing.nav.patientSignIn.body",
      },
    ],
  },
  {
    id: "source",
    labelKey: "marketing.nav.source",
    eyebrowKey: "marketing.nav.source.eyebrow",
    items: [
      {
        href: REPO,
        titleKey: "marketing.nav.repo.title",
        bodyKey: "marketing.nav.repo.body",
        external: true,
      },
      {
        href: `${REPO}/tree/main/docs`,
        titleKey: "marketing.nav.docs.title",
        bodyKey: "marketing.nav.docs.body",
        external: true,
      },
      {
        href: `${REPO}/issues`,
        titleKey: "marketing.nav.issues.title",
        bodyKey: "marketing.nav.issues.body",
        external: true,
      },
    ],
  },
];

/** Every page section the header can point at, for the scroll-spy. */
export const NAV_SECTIONS = NAV_MENUS.flatMap((m) => [m.promo, ...m.items])
  .map((item) => item?.section)
  .filter((s): s is string => Boolean(s));
