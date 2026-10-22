/** The studies the landing page's demo shows, each with the analysis a vision model
 * wrote for it. This is a copy of `platform/api/static/imaging-demo/analyses.json`
 * (the file the app's Imaging page serves): the public landing page cannot reach the
 * API, and it never calls a model. lib/__tests__/imaging-demo.test.ts fails when the
 * two drift apart. The text is the model's output, not reviewed by a clinician. */
export interface DemoStudy {
  id: string;
  /** Under /public; the same files as the landing's image gallery. */
  image: string;
  modality: string;
  region: string;
  model: string;
  description: string;
}

export const DEMO_STUDIES: DemoStudy[] = [
  {
    id: "xray",
    image: "/landing/analysis/xray.webp",
    modality: "XRAY",
    region: "Chest",
    model: "gemini-flash-latest",
    description:
      "This is a frontal chest radiograph (or stylized/inverted-color X-ray image) capturing the thoracic cage, bilateral shoulders, and upper abdomen. The visual field includes the cervical and thoracic spine, ribs, clavicles, scapulae, and proximal humeri. Bilateral lung fields appear grossly radiolucent without overt focal consolidation, though parenchymal vascular markings are poorly delineated, suggesting artificial processing or non-standard windowing. The cardiac silhouette is centrally oriented, and the mediastinal contours remain within typical limits. The left hemidiaphragm demonstrates an underlying prominent gastric air bubble with an air-fluid level. No obvious gross fractures or dislocations are identified in the visualized osseous structures; however, clinical correlation with standard diagnostic-grade imaging is warranted due to the non-standard contrast and color tone.",
  },
  {
    id: "ct-brain",
    image: "/landing/analysis/ct-brain.webp",
    modality: "CT",
    region: "Brain",
    model: "gemini-flash-latest",
    description:
      "This image shows a non-contrast computed tomography (CT) scan of the head, presented primarily as a sagittal reformatted view with an axial localizer inset (soft-tissue window). The field of view includes the neurocranium, brain parenchyma, facial structures, and upper cervical spine. \n\nA prominent collection of intracranial air (pneumocephalus) is visible along the anterior frontal extra-axial space. On the axial inset, this air creates bilateral compression and separation of the frontal lobes, resembling the Mount Fuji sign, which is indicative of tension pneumocephalus. No gross midline shift is apparent on the axial view, though ventricular compression is noted. The surrounding calvarium, skull base, and adjacent paranasal sinuses warrant careful assessment for an underlying fracture, defect, or post-surgical changes.",
  },
  {
    id: "mri-brain",
    image: "/landing/analysis/mri-brain.webp",
    modality: "MRI",
    region: "Brain",
    model: "gemini-flash-latest",
    description:
      "This axial brain MRI demonstrates a large intra-axial mass centered within the right cerebral hemisphere, involving the deep frontotemporal/basal ganglia region. The lesion consists of a prominent, heterogeneous, markedly hyperintense core with lobulated margins, surrounded by an extensive rim of hypointensity consistent with vasogenic edema. Significant local mass effect is evident, with compression and partial effacement of the frontal horn and body of the right lateral ventricle. There is secondary midline shift toward the left and effacement of the adjacent cerebral sulci. The left cerebral hemisphere and posterior fossa structures, where visualized, appear largely unremarkable. These findings warrant comprehensive multiplanar and contrast-enhanced review.",
  },
  {
    id: "ultrasound",
    image: "/landing/analysis/ultrasound.webp",
    modality: "ULTRASOUND",
    region: "Obstetric",
    model: "gemini-flash-latest",
    description:
      "This is a sagittal-plane, B-mode obstetric ultrasound image of a gravid uterus demonstrating a single intrauterine fetus in a first-trimester profile view. The fetal head is positioned to the right, showing an intact calvarial contour and early intracranial structures, with facial profile features faintly visible. The fetal torso, back, and partially flexed lower extremities are visible toward the left within an adequate pocket of anechoic amniotic fluid. The posterior nuchal region is visible, though specific measurement calipers are not placed. No gross contour abnormalities or amniotic fluid deficiencies are definitively identified on this single representative view, though comprehensive biometric evaluation requires dedicated real-time scanning.",
  },
];
