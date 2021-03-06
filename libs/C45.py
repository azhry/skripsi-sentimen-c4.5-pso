from math import log
from collections import Counter
from entities.Node import Node
import numpy as np, sys

class C45:
	"""
	Class yang digunakan untuk membangun model C4.5 untuk klasifikasi kelas sentimen

	Attributes:
		vectors (TFIDF): objek yang menangani perhitungan tfidf
		data (DataFrame): objek data yang berisi review dan label
		npdata (2d-numpy): matrix data yang berisi review dan label
		totalEntropy (double): entropy total
		weights (2d-numpy): matrix hasil perhitungan tfidf
		termsInfo (dict): dictionary atribut beserta index-nya
		attributes (list): daftar atribut-atribut yang didapatkan dari proses tfidf
		tree (Node): objek tree
		scores (double): nilai skor akurasi hasil klasifikasi
	"""

	def __init__(self, vectors, data):
		"""
		Constructor

		Parameters:
		vectors (TFIDF): objek yang menangani perhitungan tfidf
		data (DataFrame): objek data yang berisi review dan label

		"""

		self.vectors = vectors
		self.data = data.reset_index()
		self.npdata = data.as_matrix()
		self.totalEntropy = 0
		self.weights = self.vectors.weights
		self.termsInfo = self.vectors.termIndex
		self.attributes = np.array(list(self.termsInfo.keys()))
		self.tree = None
		self.scores = 0

	def calculate_total_entropy(self):
		"""
		Menghitung entropy total

		Returns:
		void

		"""

		self.totalEntropy = 0
		labelCount = Counter(self.data["Label"])
		labelValue = list(labelCount.values())
		labelTotal = sum(labelValue)
		for value in labelValue:
			self.totalEntropy += (-1 * (value / labelTotal) * np.log10(value / labelTotal))

	def calculate_attribute_gain(self, attribute, threshold, excludedRows = ()):
		"""
		Menghitung nilai gain pada suatu atribut

		Parameters:
		attribute (string): atribut yang nilai gain-nya akan dihitung
		threshold (double): nilai threshold pada atribut
		excludedRows (tuple): data yang tidak boleh dimasukkan pada perhitungan

		Returns:
		double: nilai gain atribut 

		"""

		leftChild, rightChild = self.get_child_nodes(attribute, threshold, excludedRows)
		left = self.npdata[list(leftChild)]
		right = self.npdata[list(rightChild)]
		leftEntropy, leftTotal = self.calculate_entropy(left)
		rightEntropy, rightTotal = self.calculate_entropy(right)
		total = leftTotal + rightTotal
		info = (leftTotal / total) * leftEntropy + (rightTotal / total) * rightEntropy if total != 0 else 0
		return self.totalEntropy - info

	def calculate_entropy(self, data):
		"""
		Menghitung nilai entropy pada data dan jumlah masing-masing label pada data
		
		Parameters:
		data (numpy): data yang berisi review dan label

		Returns:
		entropy (double): nilai entropy
		labelTotal (int): total keseluruhan data

		"""

		labelCount = Counter(data[:, -1])
		labelValue = list(labelCount.values())
		labelTotal = sum(labelValue)
		entropy = sum(-1 * ((x / labelTotal) * (np.log10(x / labelTotal) if (x / labelTotal) != 0 else 0)) for x in labelValue) if labelTotal != 0 else 0
		return entropy, labelTotal

	def get_possible_thresholds(self, attribute, excludedRows = ()):
		"""
		Menghitung tiap kemungkinan nilai threshold pada atribut
	
		Parameters:
		attribute (string): atribut
		excludedRows (tuple): data yang tidak boleh dimasukkan pada perhitungan

		Returns:
		threshold (list): daftar nilai threshold pada atribut yang dihitung

		"""

		vectors = np.delete(self.weights, excludedRows, axis = 0)
		weights = vectors[:, self.termsInfo[attribute]]
		weights = sorted(set(weights))
		weightCount = len(weights)
		thresholds = []
		for i in range(weightCount - 1):
			thresholds.append((float(weights[i]) + float(weights[i + 1])) / 2)
		return thresholds

	def pruning(self, excludedRows = ()):
		"""
		Melakukan pre-pruning tree menggunakan entropy-based discretization

		Parameters:
		excludedRows (tuple): data yang tidak boleh dimasukkan pada perhitungan

		Returns:
		attrThresholds (list): daftar atribut beserta nilai threshold dan gain-nya

		"""

		attrThresholds = []
		for attr in self.attributes:
			thresholds = self.get_possible_thresholds(attr, excludedRows)
			if len(thresholds) <= 0:
				continue
			thresholdGain = []
			for threshold in thresholds:
				gain = self.calculate_attribute_gain(attr, threshold, excludedRows)
				thresholdGain.append([threshold, gain])
			thresholdGain = sorted(thresholdGain, key = lambda x: x[1], reverse = True)
			attrThreshold = [attr]
			attrThreshold.extend(thresholdGain[0])
			attrThresholds.append(attrThreshold)
		return sorted(attrThresholds, key = lambda x: x[2], reverse = True)

	def get_child_nodes(self, attribute, threshold, excludedRows = ()):
		"""
		Mendapatkan data pada tiap child pada suatu node dengan atribut tertentu

		Parameters:
		attribute (string): atribut
		threshold (double): nilai threshold pada node
		excludedRows (tuple): data yang tidak boleh dimasukkan pada perhitungan
	
		Returns:
		leftChild (numpy): data pada child kiri pada node
		rightChild (numpy): data pada child kanan pada node

		"""

		leftIdx = np.where(self.weights[:, self.termsInfo[attribute]] <= threshold)[0]
		rightIdx = np.where(self.weights[:, self.termsInfo[attribute]] > threshold)[0]
		leftChild = np.array(list(set(leftIdx) - set(excludedRows)))
		rightChild = np.array(list(set(rightIdx) - set(excludedRows)))

		return leftChild, rightChild

	def attach_node(self, excludedRows = (), parentNode = None, direction = "left"):
		"""
		Membuat tree dengan memasang node-node
	
		Parameters:
		excludedRows (tuple): data yang tidak boleh dimasukkan pada perhitungan
		parentNode (Node): parent node
		direction (string): penanda apakah child node yang akan dipasang di sebelah kiri atau kanan

		Returns:
		void

		"""

		attrThresholds = self.pruning(excludedRows)
		if len(attrThresholds) > 0:
			attr, threshold = attrThresholds[0][0], attrThresholds[0][1]

			# create new node instance
			newNode = Node(attr, threshold, "root" if self.tree is None else "branch")
			if self.tree is None:
				self.tree = newNode

			# get left and right childs for the node
			left, right = self.get_child_nodes(attr, threshold, excludedRows)

			# get data exclusion for each child
			leftExclusion = left if excludedRows == () else np.append(left, excludedRows)
			rightExclusion = right if excludedRows == () else np.append(right, excludedRows)

			# get left and right data
			leftData = self.npdata[left]
			rightData = self.npdata[right]

			# count label occurence for each child
			leftLabel, leftCount = np.unique(leftData[:, -1], return_counts = True)
			rightLabel, rightCount = np.unique(rightData[:, -1], return_counts = True)

			leftDataCount = len(left)
			rightDataCount = len(right)

			labels = np.unique(np.append(leftLabel, rightLabel))
			labelCount = len(labels)

			# attach child node
			if parentNode is not None:
				if direction == "left":
					parentNode.set_left_child(newNode)
				
				elif direction == "right":
					parentNode.set_right_child(newNode)

			# set node type to label if there is only one label
			if labelCount == 1:
				newNode.set_type("leaf")
				newNode.set_label(labels[0])
				print(f"Leaf attached: {labels[0]}")
			elif labelCount == 2:
				if len(leftLabel) == 1:
					leftLeafNode = Node("Label", threshold, "leaf")
					leftLeafNode.set_label(leftLabel[0])
					newNode.set_left_child(leftLeafNode)
					print(f"Leaf attached: {leftLabel[0]}")
				if len(rightLabel) == 1:
					rightLeafNode = Node("Label", threshold, "leaf")
					rightLeafNode.set_label(rightLabel[0])
					newNode.set_right_child(rightLeafNode)
					print(f"Leaf attached: {rightLabel[0]}")
			else:
				if rightDataCount > 0:
					if rightDataCount == 1:
						rightLeafNode = Node("Label", threshold, "leaf")
						rightLeafNode.set_label(rightLabel[0])
						newNode.set_right_child(rightLeafNode)
						print(f"Leaf attached: {rightLabel[0]}")
					else:
						self.attach_node(leftExclusion, newNode, "right")
				if leftDataCount > 0:
					if rightDataCount == 1:
						leftLeafNode = Node("Label", threshold, "leaf")
						leftLeafNode.set_label(leftLabel[0])
						newNode.set_left_child(leftLeafNode)
						print(f"Leaf attached: {leftLabel[0]}")
					else:
						self.attach_node(rightExclusion, newNode, "left")

	def train(self):
		"""
		Melakukan training C4.5
		
		Returns:
		self (C4.5): objek C4.5

		"""

		self.calculate_total_entropy()
		self.attach_node()
		return self

	def traverse(self, row, vectors, tfidf, currNode = None):
		"""
		Melakukan traversal pada tree secara rekursif
		
		Parameters:
		row (int): baris ke- pada data
		vectors (2d-numpy): matrix hasil perhitungan tfidf
		tfidf (TFIDF): objek yang menangani perhitungan tfidf
		currNode (Node): lokasi node sekarang

		Returns:
		label (string): label data jika proses traversal mencapai leaf node, selain itu return False 

		"""

		currNode = currNode or self.tree
		if currNode is not None:
			if currNode.nodeType == "leaf":
				return currNode.label
			else:
				weight = vectors[:, tfidf.termIndex[currNode.attribute]][row]
				if weight <= currNode.threshold:
					if currNode.left is None:
						if currNode.right is not None:
							return self.traverse(row, vectors, tfidf, currNode.right)
						return False
					return self.traverse(row, vectors, tfidf, currNode.left)
				else:
					if currNode.right is None:
						if currNode.left is not None:
							return self.traverse(row, vectors, tfidf, currNode.left)
						return False
					return self.traverse(row, vectors, tfidf, currNode.right)

		return False


	def show_tree(self, currNode = None, tabs = 0):
		"""
		Menampilkan tree pada console
		
		Parameters:
		currNode (Node): lokasi node sekarang
		tabs (int): total tab yang ditampilkan pada suatu baris saat print

		Returns:
		void

		"""

		currNode = currNode or self.tree
		if currNode is not None:
			if currNode.nodeType == "leaf":
				print("\t" * tabs + "" + currNode.label)
			else:
				print("\t" * tabs + "" + currNode.attribute, currNode.threshold)
				print("\t" * tabs + "" + currNode.left.attribute if currNode.left is not None else None, currNode.right.attribute if currNode.right is not None else None)
				if currNode.left is not None:
					print("Go left")
					self.show_tree(currNode.left, tabs + 1)
				if currNode.right is not None:
					print("Go right")
					self.show_tree(currNode.right, tabs + 1)

	def predict(self, tfidf, docs):
		"""
		Melakukan klasifikasi pada data
		
		Parameters:
		tfidf (TFIDF): objek yang menangani perhitungan tfidf
		docs (list): daftar review yang akan diklasifikasi

		Returns:
		label (list): daftar label hasil klasifikasi pada review

		"""

		vect = tfidf.test_tfidf(docs)
		return np.array([self.traverse(i, vect, tfidf) for i, _ in enumerate(docs)])

	def score(self, tfidf, data):
		"""
		Menghitung skor akurasi hasil klasifikasi
		
		Parameters:
		tfidf (TFIDF): objek yang menangani perhitungan tfidf
		data (DataFrame): objek yang berisi review dan label

		Returns:
		score (double): skor akurasi hasil klasifikasi

		"""

		predicted = self.predict(tfidf, data["Review"])
		actual = np.array(data["Label"])
		at, cm = np.unique(predicted == actual, return_counts=True)
		self.set_score((0 if True not in at else (cm[0] if len(at) == 1 else cm[1])) / np.sum(cm))
		return self.get_score()

	def get_score(self):
		"""
		getter score
		
		Returns:
		score (double): skor akurasi hasil klasifikasi

		"""

		return self.scores

	def set_score(self, score):
		"""
		setter score
		
		Returns:
		void

		"""

		self.scores = score