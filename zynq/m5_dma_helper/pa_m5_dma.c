// SPDX-License-Identifier: GPL-2.0
/* Temporary M5 owner for page-backed, noncoherent FPGA memory.
 *
 * The helper deliberately owns the supervisor GPIO sequence as well as the
 * Linux DMA mappings.  Userspace never supplies physical addresses and cannot
 * return the pages to CPU ownership until the fabric reports a complete drain.
 */
#include <linux/delay.h>
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/uaccess.h>

#include "pa_m5_dma_uapi.h"

#define PA_M5_PAGE_COUNT (PA_M5_ARENA_BYTES / PA_M5_PAGE_BYTES)
#define PA_M5_PTE_BYTES (PA_M5_PAGE_COUNT * sizeof(u32))

#define PA_M5_CONTROL_PHYS 0x41200000U
#define PA_M5_TABLE_PHYS   0x41210000U
#define PA_M5_ARENA_PHYS   0x41220000U
#define PA_M5_STATUS_PHYS  0x41230000U
#define PA_M5_GPIO_BYTES   0x00010000U

#define PA_M5_CTL_CLUSTER_N BIT(0)
#define PA_M5_CTL_CORE_N    BIT(1)
#define PA_M5_CTL_MAP       BIT(2)
#define PA_M5_CTL_FLUSH     BIT(3)
#define PA_M5_CTL_ABORT     BIT(4)

#define PA_M5_ST_FLUSH_READY BIT(0)
#define PA_M5_ST_BUSY        BIT(1)
#define PA_M5_ST_QUIESCED    BIT(2)
#define PA_M5_ST_POISONED    BIT(3)

struct pa_m5_page {
	struct page *page;
	dma_addr_t dma;
	bool mapped;
	bool writable;
};

struct pa_m5_session {
	struct pa_m5_page *pages;
	u32 *ptes;
	dma_addr_t ptes_dma;
	u32 allocated_pages;
	enum pa_m5_owner owner;
	bool unsafe_ref;
};

static DEFINE_MUTEX(pa_m5_lock);
static struct pa_m5_session pa_m5;
static bool pa_m5_opened;
static void __iomem *control_regs;
static void __iomem *table_regs;
static void __iomem *arena_regs;
static void __iomem *status_regs;
static u64 pa_m5_dma_mask = DMA_BIT_MASK(32);

static struct miscdevice pa_m5_misc;

static u32 pa_m5_status(void)
{
	return ioread32(status_regs);
}

static void pa_m5_control(u32 value)
{
	iowrite32(value, control_regs);
	(void)ioread32(control_regs);
}

static int pa_m5_wait_status(u32 required, u32 forbidden)
{
	unsigned int tries;

	for (tries = 0; tries < 2000; ++tries) {
		u32 status = pa_m5_status();

		if ((status & required) == required && !(status & forbidden))
			return 0;
		usleep_range(500, 1000);
	}
	return -ETIMEDOUT;
}

static int pa_m5_prepare_locked(void)
{
	if (pa_m5.owner != PA_M5_OWNER_CPU)
		return -EBUSY;

	/* A short full reset clears sticky cancellation.  Abort remains asserted
	 * when the IO domain is released, and the harts remain stopped. */
	pa_m5_control(PA_M5_CTL_ABORT);
	udelay(10);
	pa_m5_control(PA_M5_CTL_ABORT | PA_M5_CTL_CLUSTER_N);
	return pa_m5_wait_status(PA_M5_ST_QUIESCED,
				 PA_M5_ST_BUSY | PA_M5_ST_POISONED);
}

static void pa_m5_free_locked(void)
{
	u32 index;
	struct device *device = pa_m5_misc.this_device;

	if (pa_m5.owner != PA_M5_OWNER_CPU)
		return;
	if (pa_m5.pages) {
		for (index = 0; index < PA_M5_PAGE_COUNT; ++index) {
			struct pa_m5_page *entry = &pa_m5.pages[index];

			if (!entry->mapped)
				continue;
			dma_unmap_page(device, entry->dma, PAGE_SIZE,
				       DMA_BIDIRECTIONAL);
			__free_page(entry->page);
		}
		kvfree(pa_m5.pages);
	}
	if (pa_m5.ptes)
		dma_free_coherent(device, PA_M5_PTE_BYTES, pa_m5.ptes,
				  pa_m5.ptes_dma);
	memset(&pa_m5, 0, sizeof(pa_m5));
}

static int pa_m5_ensure_table_locked(void)
{
	struct device *device = pa_m5_misc.this_device;

	if (pa_m5.pages)
		return 0;
	pa_m5.pages = kvcalloc(PA_M5_PAGE_COUNT, sizeof(*pa_m5.pages),
				 GFP_KERNEL);
	if (!pa_m5.pages)
		return -ENOMEM;
	pa_m5.ptes = dma_alloc_coherent(device, PA_M5_PTE_BYTES,
					 &pa_m5.ptes_dma, GFP_KERNEL);
	if (!pa_m5.ptes || pa_m5.ptes_dma > U32_MAX ||
	    pa_m5.ptes_dma + PA_M5_PTE_BYTES - 1 > U32_MAX) {
		if (pa_m5.ptes)
			dma_free_coherent(device, PA_M5_PTE_BYTES, pa_m5.ptes,
					  pa_m5.ptes_dma);
		pa_m5.ptes = NULL;
		kvfree(pa_m5.pages);
		pa_m5.pages = NULL;
		return -ENOMEM;
	}
	memset(pa_m5.ptes, 0, PA_M5_PTE_BYTES);
	pa_m5.owner = PA_M5_OWNER_CPU;
	return 0;
}

static int pa_m5_alloc_region_locked(const struct pa_m5_dma_region *region)
{
	struct device *device = pa_m5_misc.this_device;
	u64 end = (u64)region->offset + region->bytes;
	u32 first, count, done;
	int ret;

	if (pa_m5.owner != PA_M5_OWNER_CPU)
		return -EBUSY;
	if (!region->bytes || region->reserved ||
	    region->flags & ~PA_M5_REGION_WRITE ||
	    (region->offset | region->bytes) & (PAGE_SIZE - 1) ||
	    end > PA_M5_ARENA_BYTES)
		return -EINVAL;
	ret = pa_m5_ensure_table_locked();
	if (ret)
		return ret;
	first = region->offset >> PAGE_SHIFT;
	count = region->bytes >> PAGE_SHIFT;
	for (done = 0; done < count; ++done)
		if (pa_m5.pages[first + done].mapped)
			return -EEXIST;

	for (done = 0; done < count; ++done) {
		struct pa_m5_page *entry = &pa_m5.pages[first + done];
		dma_addr_t dma;

		entry->page = alloc_page(GFP_KERNEL | __GFP_ZERO | __GFP_NOWARN |
					 __GFP_NORETRY);
		if (!entry->page) {
			ret = -ENOMEM;
			goto rollback;
		}
		dma = dma_map_page(device, entry->page, 0, PAGE_SIZE,
				   DMA_BIDIRECTIONAL);
		if (dma_mapping_error(device, dma) || dma > U32_MAX ||
		    (dma & (PAGE_SIZE - 1))) {
			if (!dma_mapping_error(device, dma))
				dma_unmap_page(device, dma, PAGE_SIZE,
					       DMA_BIDIRECTIONAL);
			__free_page(entry->page);
			entry->page = NULL;
			ret = -EIO;
			goto rollback;
		}
		entry->dma = dma;
		/* Allocation returns CPU-owned storage to userspace. dma_map_page
		 * initially transfers ownership to the device even before START. */
		dma_sync_single_for_cpu(device, dma, PAGE_SIZE, DMA_BIDIRECTIONAL);
		entry->mapped = true;
		entry->writable = !!(region->flags & PA_M5_REGION_WRITE);
		pa_m5.ptes[first + done] = (u32)dma | BIT(0) |
			(entry->writable ? BIT(1) : 0);
		++pa_m5.allocated_pages;
	}
	return 0;

rollback:
	while (done--) {
		struct pa_m5_page *entry = &pa_m5.pages[first + done];

		pa_m5.ptes[first + done] = 0;
		dma_unmap_page(device, entry->dma, PAGE_SIZE,
			       DMA_BIDIRECTIONAL);
		__free_page(entry->page);
		memset(entry, 0, sizeof(*entry));
		--pa_m5.allocated_pages;
	}
	return ret;
}

static void pa_m5_sync_for_device_locked(void)
{
	struct device *device = pa_m5_misc.this_device;
	u32 index;

	for (index = 0; index < PA_M5_PAGE_COUNT; ++index)
		if (pa_m5.pages[index].mapped)
			dma_sync_single_for_device(device, pa_m5.pages[index].dma,
						   PAGE_SIZE, DMA_BIDIRECTIONAL);
}

static void pa_m5_sync_for_cpu_locked(void)
{
	struct device *device = pa_m5_misc.this_device;
	u32 index;

	for (index = 0; index < PA_M5_PAGE_COUNT; ++index)
		if (pa_m5.pages[index].mapped)
			dma_sync_single_for_cpu(device, pa_m5.pages[index].dma,
						PAGE_SIZE, DMA_BIDIRECTIONAL);
}

static int pa_m5_start_locked(void)
{
	int ret;

	if (pa_m5.owner != PA_M5_OWNER_CPU || !pa_m5.pages ||
	    !pa_m5.allocated_pages)
		return -EINVAL;
	ret = pa_m5_prepare_locked();
	if (ret)
		return ret;
	iowrite32((u32)pa_m5.ptes_dma, table_regs);
	iowrite32(PA_M5_ARENA_BYTES, arena_regs);
	(void)ioread32(arena_regs);
	pa_m5_sync_for_device_locked();
	dma_wmb();
	pa_m5.owner = PA_M5_OWNER_DEVICE;
	if (!pa_m5.unsafe_ref) {
		__module_get(THIS_MODULE);
		pa_m5.unsafe_ref = true;
	}

	/* PREPARE/drain leaves the packet mover in sticky Stopped. Clear it
	 * with a fully drained IO reset, lowering abort BEFORE IO release.
	 * Core reset alone cannot clear the mover; holding abort through IO
	 * release would immediately stop it again. Cores stay held throughout. */
	pa_m5_control(PA_M5_CTL_MAP);
	udelay(10);
	pa_m5_control(PA_M5_CTL_CLUSTER_N | PA_M5_CTL_MAP | PA_M5_CTL_FLUSH);
	ret = pa_m5_wait_status(PA_M5_ST_FLUSH_READY,
				 PA_M5_ST_BUSY | PA_M5_ST_POISONED);
	if (ret)
		return ret;
	pa_m5_control(PA_M5_CTL_CLUSTER_N | PA_M5_CTL_MAP);
	pa_m5_control(PA_M5_CTL_CLUSTER_N | PA_M5_CTL_CORE_N | PA_M5_CTL_MAP);
	return 0;
}

static int pa_m5_return_cpu_locked(void)
{
	int ret;

	if (pa_m5.owner == PA_M5_OWNER_CPU)
		return 0;
	if (pa_m5.owner != PA_M5_OWNER_DEVICE &&
	    pa_m5.owner != PA_M5_OWNER_UNSAFE)
		return -EINVAL;

	/* Stop admission and request global cancellation/drain in one write. */
	pa_m5.owner = PA_M5_OWNER_UNSAFE;
	pa_m5_control(PA_M5_CTL_CLUSTER_N | PA_M5_CTL_MAP | PA_M5_CTL_ABORT);
	ret = pa_m5_wait_status(PA_M5_ST_QUIESCED,
				 PA_M5_ST_BUSY | PA_M5_ST_POISONED);
	if (ret)
		return ret;
	pa_m5_control(PA_M5_CTL_CLUSTER_N | PA_M5_CTL_ABORT);
	pa_m5_sync_for_cpu_locked();
	pa_m5.owner = PA_M5_OWNER_CPU;
	if (pa_m5.unsafe_ref) {
		pa_m5.unsafe_ref = false;
		module_put(THIS_MODULE);
	}
	return 0;
}

static int pa_m5_open(struct inode *inode, struct file *file)
{
	int ret = 0;

	mutex_lock(&pa_m5_lock);
	if (pa_m5_opened || pa_m5.owner != PA_M5_OWNER_CPU)
		ret = -EBUSY;
	else
		pa_m5_opened = true;
	mutex_unlock(&pa_m5_lock);
	return ret;
}

static int pa_m5_release(struct inode *inode, struct file *file)
{
	mutex_lock(&pa_m5_lock);
	if (pa_m5.owner != PA_M5_OWNER_CPU)
		(void)pa_m5_return_cpu_locked();
	if (pa_m5.owner == PA_M5_OWNER_CPU)
		pa_m5_free_locked();
	pa_m5_opened = false;
	mutex_unlock(&pa_m5_lock);
	return 0;
}

static long pa_m5_ioctl(struct file *file, unsigned int command,
			unsigned long argument)
{
	struct pa_m5_dma_region region;
	struct pa_m5_dma_info info;
	int ret = 0;

	mutex_lock(&pa_m5_lock);
	switch (command) {
	case PA_M5_DMA_ALLOC_REGION:
		if (copy_from_user(&region, (void __user *)argument, sizeof(region))) {
			ret = -EFAULT;
			break;
		}
		ret = pa_m5_alloc_region_locked(&region);
		break;
	case PA_M5_DMA_GET_INFO:
		memset(&info, 0, sizeof(info));
		info.abi = PA_M5_DMA_ABI;
		info.arena_bytes = PA_M5_ARENA_BYTES;
		info.pte_dma = (u32)pa_m5.ptes_dma;
		info.allocated_pages = pa_m5.allocated_pages;
		info.owner = pa_m5.owner;
		info.supervisor_status = pa_m5_status();
		info.supervisor_control = ioread32(control_regs);
		if (copy_to_user((void __user *)argument, &info, sizeof(info)))
			ret = -EFAULT;
		break;
	case PA_M5_DMA_PREPARE:
		ret = pa_m5_prepare_locked();
		break;
	case PA_M5_DMA_START:
		ret = pa_m5_start_locked();
		break;
	case PA_M5_DMA_RETURN_CPU:
		ret = pa_m5_return_cpu_locked();
		break;
	default:
		ret = -ENOTTY;
	}
	mutex_unlock(&pa_m5_lock);
	return ret;
}

static int pa_m5_mmap(struct file *file, struct vm_area_struct *vma)
{
	unsigned long first = vma->vm_pgoff;
	unsigned long count = vma_pages(vma);
	unsigned long index;
	int ret = 0;

	mutex_lock(&pa_m5_lock);
	if (pa_m5.owner != PA_M5_OWNER_CPU || !pa_m5.pages ||
	    first >= PA_M5_PAGE_COUNT || count > PA_M5_PAGE_COUNT - first) {
		ret = -EINVAL;
		goto out;
	}
	for (index = 0; index < count; ++index) {
		if (!pa_m5.pages[first + index].mapped) {
			ret = -ENXIO;
			goto out;
		}
	}
	vm_flags_set(vma, VM_DONTEXPAND | VM_DONTDUMP);
	for (index = 0; index < count; ++index) {
		ret = vm_insert_page(vma, vma->vm_start + index * PAGE_SIZE,
				     pa_m5.pages[first + index].page);
		if (ret)
			break;
	}
out:
	mutex_unlock(&pa_m5_lock);
	return ret;
}

static const struct file_operations pa_m5_fops = {
	.owner = THIS_MODULE,
	.open = pa_m5_open,
	.release = pa_m5_release,
	.unlocked_ioctl = pa_m5_ioctl,
	.mmap = pa_m5_mmap,
	.llseek = no_llseek,
};

static struct miscdevice pa_m5_misc = {
	.minor = MISC_DYNAMIC_MINOR,
	.name = "pocketai_m5",
	.fops = &pa_m5_fops,
	.mode = 0600,
};

static int __init pa_m5_init(void)
{
	int ret;
	struct device *device;

	BUILD_BUG_ON(PAGE_SIZE != PA_M5_PAGE_BYTES);
	ret = misc_register(&pa_m5_misc);
	if (ret)
		return ret;
	device = pa_m5_misc.this_device;
	device->dma_mask = &pa_m5_dma_mask;
	device->coherent_dma_mask = DMA_BIT_MASK(32);
	ret = dma_set_mask_and_coherent(device, DMA_BIT_MASK(32));
	if (ret)
		goto fail_misc;
	control_regs = ioremap(PA_M5_CONTROL_PHYS, PA_M5_GPIO_BYTES);
	table_regs = ioremap(PA_M5_TABLE_PHYS, PA_M5_GPIO_BYTES);
	arena_regs = ioremap(PA_M5_ARENA_PHYS, PA_M5_GPIO_BYTES);
	status_regs = ioremap(PA_M5_STATUS_PHYS, PA_M5_GPIO_BYTES);
	if (!control_regs || !table_regs || !arena_regs || !status_regs) {
		ret = -ENOMEM;
		goto fail_iomap;
	}
	pr_info("pocketai_m5: DMA owner ABI %u ready\n", PA_M5_DMA_ABI);
	return 0;

fail_iomap:
	if (status_regs)
		iounmap(status_regs);
	if (arena_regs)
		iounmap(arena_regs);
	if (table_regs)
		iounmap(table_regs);
	if (control_regs)
		iounmap(control_regs);
fail_misc:
	misc_deregister(&pa_m5_misc);
	return ret;
}

static void __exit pa_m5_exit(void)
{
	mutex_lock(&pa_m5_lock);
	pa_m5_free_locked();
	mutex_unlock(&pa_m5_lock);
	iounmap(status_regs);
	iounmap(arena_regs);
	iounmap(table_regs);
	iounmap(control_regs);
	misc_deregister(&pa_m5_misc);
}

module_init(pa_m5_init);
module_exit(pa_m5_exit);
MODULE_LICENSE("GPL");
MODULE_AUTHOR("PocketAI-T");
MODULE_DESCRIPTION("Owned scatter-page DMA arena and supervisor for M5");
