#ifndef PA_M5_DMA_UAPI_H
#define PA_M5_DMA_UAPI_H

#include <linux/ioctl.h>
#include <linux/types.h>

#define PA_M5_DMA_ABI 1U
#define PA_M5_ARENA_BYTES 0x10000000U
#define PA_M5_PAGE_BYTES 4096U
#define PA_M5_REGION_WRITE 1U

enum pa_m5_owner {
	PA_M5_OWNER_CPU = 0,
	PA_M5_OWNER_DEVICE = 1,
	PA_M5_OWNER_UNSAFE = 2,
};

struct pa_m5_dma_region {
	__u32 offset;
	__u32 bytes;
	__u32 flags;
	__u32 reserved;
};

struct pa_m5_dma_info {
	__u32 abi;
	__u32 arena_bytes;
	__u32 pte_dma;
	__u32 allocated_pages;
	__u32 owner;
	__u32 supervisor_status;
	__u32 supervisor_control;
	__u32 reserved;
};

#define PA_M5_DMA_IOC_MAGIC 'P'
#define PA_M5_DMA_ALLOC_REGION _IOW(PA_M5_DMA_IOC_MAGIC, 0x01, struct pa_m5_dma_region)
#define PA_M5_DMA_GET_INFO _IOR(PA_M5_DMA_IOC_MAGIC, 0x02, struct pa_m5_dma_info)
#define PA_M5_DMA_PREPARE _IO(PA_M5_DMA_IOC_MAGIC, 0x03)
#define PA_M5_DMA_START _IO(PA_M5_DMA_IOC_MAGIC, 0x04)
#define PA_M5_DMA_RETURN_CPU _IO(PA_M5_DMA_IOC_MAGIC, 0x05)

#endif
