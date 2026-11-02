import katex from "manimflow-katex";

// One stylesheet for the whole page, next to the module so its fonts load from there too.
function addStylesheet() {
  if (document.getElementById("manimflow-katex-css")) return;
  const link = document.createElement("link");
  link.id = "manimflow-katex-css";
  link.rel = "stylesheet";
  link.href = import.meta.resolve("manimflow-katex/katex.min.css");
  document.head.appendChild(link);
}

export default {
  template: `<span></span>`,
  props: {
    latex: String,
  },
  mounted() {
    addStylesheet();
    this.draw();
  },
  watch: {
    latex() {
      this.draw();
    },
  },
  methods: {
    draw() {
      // Broken LaTeX shows up in red instead of leaving a blank.
      katex.render(this.latex, this.$el, { throwOnError: false });
    },
  },
};
