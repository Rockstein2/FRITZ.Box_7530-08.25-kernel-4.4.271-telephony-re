# SPDX-License-Identifier: GPL-2.0-only
#
# Minimal FRITZ!Box 7530 FON TDM diagnostic transport.
#
# The source is kept in ../../../../src/fon-driver and symlinked here so the
# canonical driver and the OpenWrt package cannot drift silently.

include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/kernel.mk

PKG_NAME:=fon-tdm
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
PKG_MAINTAINER:=FRITZ!Box 7530 FON reverse-engineering project

include $(INCLUDE_DIR)/package.mk

define KernelPackage/fon-tdm
  SUBMENU:=Other modules
  TITLE:=FRITZ!Box 7530 FON TDM diagnostic transport
  DEPENDS:=@TARGET_ipq40xx
  FILES:=$(PKG_BUILD_DIR)/fon_tdm_drv.ko
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
	$(CP) $(CURDIR)/src/Makefile $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_tdm.c $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_tdm.h $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_dma.c $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_dma.h $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_hw.c $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_hw.h $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_c1.c $(PKG_BUILD_DIR)/
	$(CP) $(CURDIR)/src/fon_c1.h $(PKG_BUILD_DIR)/
endef

define Build/Compile
	$(MAKE) -C "$(LINUX_DIR)" \
		$(KERNEL_MAKE_FLAGS) \
		M="$(PKG_BUILD_DIR)" \
		CONFIG_FON_TDM=m \
		modules
endef

$(eval $(call KernelPackage,fon-tdm))
