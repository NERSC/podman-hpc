#
# spec file for package podman-hpc
#
# Copyright (c) 2022
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.


%global modname podman_hpc                                                           1


Name:           podman-hpc
Version:        1.0.0
Release:        1
Summary:	Scripts to enable Podman to run in an HPC environment
# FIXME: Select a correct license from https://github.com/openSUSE/spec-cleaner#spdx-licenses
License:        Apache 2.0 
URL:            https://github.com/nersc/podman-hpc 
Source:         podman-hpc-1.0.0.tar.gz
BuildRequires:  python3

%description
Podman-hpc is a set of scripts around podman to enable it to work
effectively and scale in an HPC environment.  It is designed to
run fully unprivileged.

%prep
%setup -q

%build

%install
%makeinstall

%post
%postun

%files
%license LICENSE
%doc CHANGELOG.md README.md
%config /etc/podman_hpc/nersc-plug.yaml
%config /etc/podman_hpc/01-gpu.conf
%config /etc/podman_hpc/02-mpich.conf
/usr/bin/podman-hpc
/usr/bin/hook_tool
/usr/bin/fuse-overlayfs-wrap
%{python3_sitelib}
#%{python3_sitelib}/%{modname}-%{version}*
/usr/share/containers/oci/hooks.d/02-hook_tool.json


%changelog

