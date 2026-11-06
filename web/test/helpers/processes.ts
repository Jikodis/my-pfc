/** True once no process has this pid, polled for up to two seconds. */
export async function gone(pid: number): Promise<boolean> {
  for (let n = 0; n < 40; n++) {
    try {
      process.kill(pid, 0)
    } catch {
      return true
    }
    await new Promise((r) => setTimeout(r, 50))
  }
  return false
}
