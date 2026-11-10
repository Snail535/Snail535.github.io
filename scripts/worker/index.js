import { handle } from "./handler.js";

export default {
  fetch(request, env) {
    return handle(request, env);
  },
};
