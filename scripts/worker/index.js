import { handle } from "./handler.js";

export default {
  fetch(request, env, ctx) {
    return handle(request, env, Date.now(), ctx);
  },
};
