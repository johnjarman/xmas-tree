venv: venv/make

venv/make: requirements.txt
	python -m venv venv
	. venv/bin/activate; pip install -Ur requirements.txt
	touch venv/make

.PHONY: install
install: venv
	sudo cp index.html /var/www/html/
	sudo systemctl enable xmastree.service

.PHONY: clean
clean:
	rm -rf venv
	find -iname "*.pyc" -delete