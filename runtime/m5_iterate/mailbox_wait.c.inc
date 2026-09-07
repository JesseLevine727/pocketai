/* The runtime is machine-mode, with a fatal trap handler. Enable only the
 * local external wake mask, NOT global interrupts. Ibex WFI resumes on the
 * locally enabled pending level even with mstatus.MIE=0; it does not trap.
 * The level remains asserted until this receiver acknowledges it, so an
 * arrival between the predicate load and WFI cannot be lost. Other external
 * sources/spurious wakeups must not be mistaken for mailbox completion. */
static void pa_iter_enable_mailbox_wait(void) {
  __asm__ volatile("csrc mstatus, %0\ncsrs mie, %1"
                   :: "r"(8u), "r"(2048u) : "memory");
}

static void pa_iter_wait_mailbox(uint32_t mask) {
  while (!(*(volatile uint32_t *)UINT32_C(0x00012008) & mask))
    __asm__ volatile("wfi" ::: "memory");
}
