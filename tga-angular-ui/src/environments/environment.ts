export const environment = {
  production: false,

  // Use the real FastAPI retrieval and chat pipelines.
  useMockApi: false,

  // Change this when your backend uses a different host/port.
  apiBaseUrl: 'http://localhost:8000/api',

  // Replace after creating a Google Web OAuth client.
  googleClientId: "636198143323-6lgi4b9b4ssv16upslr2980d7b3v4bci.apps.googleusercontent.com",
};
