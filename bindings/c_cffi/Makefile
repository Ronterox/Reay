# cffi API-mode build -> ../build/c_cffi/{aigame/__init__.py, aigame/_aigame_cffi*.so}
PY  := $(abspath ../../.venv/bin/python)
OUT := $(abspath ../build/c_cffi)

all:
	rm -rf $(OUT)
	mkdir -p $(OUT)/aigame
	cp aigame/__init__.py $(OUT)/aigame/
	TMP=$$(mktemp -d) && \
	  $(PY) $(abspath build_ffi.py) $$TMP && \
	  cp $$TMP/aigame/_aigame_cffi*.so $(OUT)/aigame/ ; rc=$$?; rm -rf $$TMP; exit $$rc

clean:
	rm -rf $(OUT)

.PHONY: all clean
