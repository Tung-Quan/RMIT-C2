const DIRECT_DOCUMENTS_COMPANY = "Personal Documents";
const DIRECT_DOCUMENTS_POSITION = "Reusable candidate documents";
const DIRECT_DOCUMENTS_DESCRIPTION =
  "Storage area for documents uploaded directly from candidate job applications.";

export function isDirectDocumentsApplication(application) {
  return Boolean(
    application &&
      application.company_name === DIRECT_DOCUMENTS_COMPANY &&
      application.position_title === DIRECT_DOCUMENTS_POSITION &&
      application.job_description === DIRECT_DOCUMENTS_DESCRIPTION
  );
}

export function filterUserApplications(applications) {
  return applications.filter((application) => !isDirectDocumentsApplication(application));
}
