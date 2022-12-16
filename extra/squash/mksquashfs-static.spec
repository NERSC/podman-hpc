#
# spec file for package mksquashfs-static
#
# Copyright (c) 2022 SUSE LLC
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via https://bugs.opensuse.org/
#


Name:           mksquashfs-static
Version:        4.5
Release:        1
Summary:	Staticalled linked mksquashfs
# FIXME: Select a correct license from https://github.com/openSUSE/spec-cleaner#spdx-licenses
License:        GPLv2
URL:            https://github.com/plougher/squashfs-tools/
Source:         mksquashfs.static

%description

%prep
cp %{SOURCE0} .

%build

%install
mkdir -p $RPM_BUILD_ROOT/usr/bin
install mksquashfs.static $RPM_BUILD_ROOT/usr/bin

%post
%postun

%files
/usr/bin/mksquashfs.static

%changelog

