// Answer profile for Greenhouse forms.
// Dropdown interaction follows fill_select() in
// https://github.com/devdattatalele/Greenhouse-AI/blob/main/webfiller.py
// Rules match the question label, because question_* ids change per job.

var GREENHOUSE_PROFILE = {
  personal: {
    firstName: "",
    lastName: "",
    preferredName: "",
    email: "",
    phone: "",
    linkedin: "",
    website: "",
    location: "",
    company: "",
    address: "",
    country: "",
  },

  // Voluntary demographic dropdowns. Leave blank to skip.
  // Option text must match the menu, as in the repo's dropdowns dict.
  eeoc: {
    gender: "",
    hispanic_ethnicity: "",
    veteran_status: "",
    disability_status: "",
  },

  // First matching rule wins. Put the more specific phrase above a broader one.
  dropdownRules: [
    { includes: "comfortable interviewing for the salary", value: "Yes" },
    { includes: "right to work", value: "Yes" },
    { includes: "legally authorized to work", value: "Yes" },
    { includes: "eligible to work", value: "Yes" },
    { includes: "sponsorship to work in the united states", value: "No" },
    { includes: "sponsorship to work in the country", value: "No" },
    { includes: "require sponsorship", value: "No" },
    { includes: "visa sponsorship", value: "No" },
    { includes: "open to working 3 days", value: "Yes" },
    { includes: "former coreweave employee", value: "No" },
    { includes: "ever been employed", value: "No" },
    { includes: "u.s. person", value: "Yes" },
    { includes: "previously employed", value: "No" },
  ],

  textRules: [
    { includes: "preferred first name", field: "preferredName" },
    { includes: "linkedin", field: "linkedin" },
    { includes: "website", field: "website" },
    { includes: "portfolio", field: "website" },
    { includes: "currently located", field: "location" },
    { includes: "city, state", field: "location" },
    { includes: "current company", field: "company" },
    { includes: "legal address", field: "address" },
    { includes: "github", field: "github" },
  ],
};

function buildGreenhouseProfile(personal, options) {
  var base = GREENHOUSE_PROFILE;
  var mergedPersonal = Object.assign({}, base.personal, personal || {});
  return {
    personal: mergedPersonal,
    eeoc: Object.assign({}, base.eeoc, (options && options.eeoc) || {}),
    fillEeoc: !!(options && options.fillEeoc),
    dropdownRules: base.dropdownRules,
    textRules: base.textRules,
    resume: (options && options.resume) || null,
  };
}
