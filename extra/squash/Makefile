


rpm: mksquashfs.static
	mkdir -p $(HOME)/rpmbuild/SOURCES/
	cp -a mksquashfs.static $(HOME)/rpmbuild/SOURCES/
	rpmbuild -ba mksquashfs-static.spec
	

mksquashfs.static:
	podman build -t mksq .
	podman run -it --rm -v $(shell pwd):/d  mksq cp /usr/local/bin/mksquashfs /d/mksquashfs.static
	
