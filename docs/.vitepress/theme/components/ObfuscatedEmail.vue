<script setup lang="ts">
import { onMounted, ref } from "vue";

// The contact address is stored reversed and base64-encoded so it never
// appears as a parseable e-mail in the statically rendered HTML that crawlers
// fetch. It is decoded only in the browser, after mount, and turned into a
// real mailto link. Decode locally with:  atob(PAYLOAD) -> reverse.
//   reverse("jbarmettler@proton.me") -> base64
const PAYLOAD = "ZW0ubm90b3JwQHJlbHR0ZW1yYWJq";

const email = ref<string | null>(null);

onMounted(() => {
  email.value = atob(PAYLOAD).split("").reverse().join("");
});
</script>

<template>
  <a v-if="email" :href="'mailto:' + email">{{ email }}</a>
  <!--
    No-JS / pre-hydration fallback. Human-readable but de-tokenised so e-mail
    regex harvesters can't lift it directly. Keeps the impressum contact
    reachable even with JavaScript disabled.
  -->
  <span v-else aria-label="contact e-mail address"
    >jbarmettler<!-- -->&#32;[at]&#32;proton<!-- -->&#32;[dot]&#32;me</span
  >
</template>
