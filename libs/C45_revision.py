from core.Database import Database
from libs.TFIDF_revision import TFIDF_revision
from entities.Node import Node
from math import log
import numpy as np

class C45_revision():

	def __init__(self, trainData, testData, foldNumber = 0):
		self.trainData 		= np.array(trainData)
		self.testData		= np.array(testData)
		self.termData		= {}
		self.excludedData	= {}
		self.foldNumber 	= foldNumber
		self.attributes 	= []
		self.db 			= Database("localhost", "root", "", "sentimen_test")
		self.totalEntropy 	= 0
		self.tree 			= None

	def constructAttributes(self):
		self.db.multiplesql("DELETE FROM attributes WHERE fold_number = " + str(self.foldNumber))
		for review in self.trainData[:,1]:
			attributes = review.split(" ")
			self.attributes.extend(attributes)

		self.attributes = set(self.attributes)
		for attribute in self.attributes:
			self.excludedData[attribute] = []
			sql = "INSERT INTO attributes(attribute, active, fold_number) VALUES('" + attribute + "', 1, " + str(self.foldNumber) + ")"
			self.db.multiplesql(sql)

	def retrieveAttributes(self):
		# check if attributes are already constructed before
		if len(self.attributes) <= 0:
			attributes = self.db.select("attributes", "fold_number = " + str(self.foldNumber))
			for attr in attributes:
				self.excludedData[attr[1]] = []
				self.attributes.append(attr[1])
		
		# otherwise construct new attributes
		else:
			self.constructAttributes()

	def calculateWeights(self):

		print("Calculating weights...")
		self.constructAttributes()

		self.tfidf = TFIDF_revision(self.trainData, self.attributes)
		self.tfidf.calculateTfIdf()
		self.tfidf.saveWeight(self.foldNumber)

	def calculateTotalEntropy(self):
		data = self.db.query("SELECT label, COUNT(id) AS total FROM preprocessed_data WHERE fold_number = " + str(self.foldNumber) + " GROUP BY label")
		length = 0
		for row in data:
			length += int(row[1])
		self.totalEntropy = 0
		for row in data:
			self.totalEntropy += (-1 * (row[1] / length) * log(row[1] / length, 10))

	def getDocumentsVector(self):
		print("Retrieving...")
		self.data = self.db.query("SELECT id_document, attribute, weight FROM weights WHERE fold_number = " + str(self.foldNumber))
		print("Retrieved")

	def getPossibleThresholds(self, attribute, excludedData = []):
		# self.termData[attribute] = self.data[self.data[:,1] == attribute]
		possibleWeights = sorted(set([x[2] for x in self.data if x[1] == attribute and x[0] not in excludedData]))
		possibleThresholds = []
		for i in range(len(possibleWeights) - 1):
			possibleThresholds.append((float(possibleWeights[i]) + float(possibleWeights[i + 1])) / 2)

		return possibleThresholds
		# possible thresholds length <= 1 does not need to calculate information gain

	def getThresholdValue(self, excludedData = [], parentNodeId = None, direction = "left"):
		attributeThresholds = []
		for _, attribute in enumerate(self.attributes):
			thresholds = self.getPossibleThresholds(attribute, excludedData)
			thresholdGain = []

			for threshold in thresholds:
				gain = self.calculateAttributeGain(attribute, threshold, excludedData)
				thresholdGain.append([threshold, gain])
			
			if len(thresholdGain) > 0:
				thresholdGain = sorted(thresholdGain, key = lambda x: x[1], reverse = True)
				attributeThreshold = [attribute]
				attributeThreshold.extend(thresholdGain[0])
				attributeThresholds.append(attributeThreshold)
			else:
				pass
				# print(attribute + " does not have any threshold possible")
		
		attributeThresholds = sorted(attributeThresholds, key = lambda x: x[2], reverse = True)
		if len(attributeThresholds) > 0:
			selectedAttribute = attributeThresholds[0]
			
			nodeType = "root" if self.tree is None else "attribute"
			insertId = 0
			if self.tree is None:
				self.tree = True
				self.db.multiplesql("INSERT INTO tree_nodes(type, value, threshold, fold_number) VALUES('" + nodeType + "', '" + selectedAttribute[0] + "', " + str(selectedAttribute[1]) + ", " + str(self.foldNumber) + ")")
				insertId = self.db.insert_id()
			else:
				self.db.multiplesql("INSERT INTO tree_nodes(type, value, threshold, fold_number) VALUES('" + nodeType + "', '" + selectedAttribute[0] + "', " + str(selectedAttribute[1]) + ", " + str(self.foldNumber) + ")")
				insertId = self.db.insert_id()
				if direction == "left":
					self.db.multiplesql("UPDATE tree_nodes SET left_node = " + str(insertId) + " WHERE node_id = " + str(parentNodeId))
				elif direction == "right":
					self.db.multiplesql("UPDATE tree_nodes SET right_node = " + str(insertId) + " WHERE node_id = " + str(parentNodeId))

			print("Node added: ", selectedAttribute[0])

			left, right, leftData, rightData = self.getChildNodes(selectedAttribute[0], selectedAttribute[1], excludedData)
			leftDataCount = len(leftData)
			rightDataCount = len(rightData)
			print("Left: ", left, " , Right: ", right)

			leftUnique, leftCounts = np.unique(left, return_counts = True)
			rightUnique, rightCounts = np.unique(right, return_counts = True)

			labels = np.append(leftUnique, rightUnique)

			if len(np.unique(labels)) == 1:
				self.db.multiplesql("UPDATE tree_nodes SET type = 'label', value = '" + labels[0] + "' WHERE node_id = " + str(insertId))
			else:
				if leftDataCount > 0:
					rightData.extend(excludedData)
					self.getThresholdValue(rightData, insertId, "left")

				if rightDataCount > 0:
					leftData.extend(excludedData)
					self.getThresholdValue(leftData, insertId, "right")
				

	def getChildNodes(self, attribute, threshold, excludedData = []):
		leftData = [x[0] for x in self.data if x[1] == attribute and x[2] <= threshold and x[0] not in excludedData]
		left = np.array([x[2] for x in self.trainData if int(x[0]) in leftData])
		rightData = [x[0] for x in self.data if x[1] == attribute and x[2] > threshold and x[0] not in excludedData]
		right = np.array([x[2] for x in self.trainData if int(x[0]) in rightData])
		return left, right, leftData, rightData


	def calculateAttributeGain(self, attribute, threshold, excludedData = []):
		left, right = self.getChildNodes(attribute, threshold, excludedData)[0:2]
		
		leftUnique, leftCounts = np.unique(left, return_counts = True)
		leftTotal = sum(leftCounts)
		rightUnique, rightCounts = np.unique(right, return_counts = True)
		rightTotal = sum(rightCounts)
		total = leftTotal + rightTotal

		leftEntropy = sum(-1 * ((x / leftTotal) * (log(x / leftTotal, 10) if (x / leftTotal) != 0 else 0)) for x in leftCounts) if leftTotal != 0 else 0
		rightEntropy = sum(-1 * ((x / rightTotal) * (log(x / rightTotal, 10) if (x / rightTotal) != 0 else 0)) for x in rightCounts) if rightTotal != 0 else 0

		info = (leftTotal / total) * leftEntropy + (rightTotal / total) * rightEntropy
		gain = self.totalEntropy - info
		return gain

	def constructTree(self):
		self.db.multiplesql("DELETE FROM weights WHERE fold_number = " + str(self.foldNumber))
		self.db.multiplesql("DELETE FROM attributes WHERE fold_number = " + str(self.foldNumber))
		self.db.multiplesql("DELETE FROM tree_nodes WHERE fold_number = " + str(self.foldNumber))
		self.calculateTotalEntropy()
		self.calculateWeights()
		self.getDocumentsVector()
		self.getThresholdValue()
		print("TREE")
		print(self.tree)
		self.evaluate()

	def evaluate(self):
		idf = self.tfidf.idf
		right, wrong = 0, 0
		self.tree = self.db.query("SELECT * FROM tree_nodes WHERE fold_number = " + str(self.foldNumber))
		for data in self.testData:
			tokens = data[1].split(" ")
			tfidf_val = {}
			for token in tokens:
				tfidf_val[token] = self.tfidf.tf(token, data[1]) * (idf[token] if token in idf else 0)
			node = [x for x in self.tree if x[1] == "root" and x[6] == self.foldNumber][0]
			if self.traverseChild(node, tfidf_val[node[2]] if node[2] in tfidf_val else 0):
				right += 1
			else:
				wrong += 1

		print("Right: ", right, " , Wrong: ", wrong)

	def traverseChild(self, node, weight):
		threshold = node[3]
		if weight > threshold:
			if node[5] is not None:
				childNode = [x for x in self.tree if x[0] == node[5]] # if empty, len(childNode) == 0
		else:
			pass