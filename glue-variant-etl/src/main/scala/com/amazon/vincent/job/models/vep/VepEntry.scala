// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

package com.amazon.vincent.job.models.vep

import scala.collection.mutable

case class RankValue(rank: Option[String], total: Option[String])

object RankValue {
  def apply(value: Option[String]): Option[RankValue] = {
    value match {
      case Some(x) =>
        if (x.trim.nonEmpty) {
          val values = x.split("/")
          Some(new RankValue(values.lift(0), values.lift(1)))
        } else {
          None
        }
      case None => None
    }
  }
}

case class MutationValue(reference: Option[String], variant: Option[String])

object MutationValue {
  def apply(value: Option[String]): Option[MutationValue] = {
    value match {
      case Some(x) =>
        if (x.trim.nonEmpty) {
          val values = x.split("/")
          Some(new MutationValue(values.lift(0), values.lift(1)))
        } else None
      case None => None
    }
  }
}

case class VepEntry(
    allele: Option[String] = None,
    consequence: Option[Array[String]] = None,
    impact: Option[String] = None,
    symbol: Option[String] = None,
    gene: Option[String] = None,
    feature_type: Option[String] = None,
    feature: Option[String] = None,
    biotype: Option[String] = None,
    exon: Option[RankValue] = None,
    intron: Option[RankValue] = None,
    hgvsc: Option[String] = None,
    hgvsp: Option[String] = None,
    cdna_position: Option[String] = None,
    cds_position: Option[String] = None,
    protein_position: Option[String] = None,
    amino_acids: Option[MutationValue] = None,
    codons: Option[MutationValue] = None,
    existing_variation: Option[Array[String]] = None,
    distance: Option[String] = None,
    strand: Option[String] = None,
    flags: Option[Array[String]] = None,
    symbol_source: Option[String] = None,
    hgnc_id: Option[String] = None,
    extras: Option[Map[String, String]] = None)

object VepEntry {
  val vepFieldDelimiter = "\\|"
  val vepDelimiter = ","
  val multiValueStringDelimiter = "&"

  def fromVepInfoValue(vepString: String, order: Array[VepField]): Array[VepEntry] = {
    val vepEntries = vepString.split(vepDelimiter)
    if (!vepEntries.forall(x => x.count(_ == '|') == (order.length - 1))) {
      // using print to as this will be used within an udf.
      println(s"Insufficient vep fields in $vepString")
      Array.empty
    } else {
      vepEntries.map { fromString(_, order) }
    }
  }

  def fromString(vepString: String, order: Array[VepField]): VepEntry = {
    val vepMap: mutable.Map[VepDefaultField, String] = mutable.Map()
    val extras: mutable.Map[String, String] = mutable.Map()
    val vepValues = vepString.split(vepFieldDelimiter.toString, -1)

    for (i <- order.indices) {
      val value = vepValues(i)
      order(i) match {
        case field: VepDefaultField => vepMap.put(field, value)
        case ExtraField(name) => extras.put(name, value)
      }
    }
    fromVepMaps(vepMap.toMap, extras.toMap)
  }

  private def parseMultiValueString(value: Option[String]): Option[Array[String]] = {
    value match {
      case Some(x) =>
        if (x.trim.isEmpty) {
          None
        } else {
          Some(x.split(multiValueStringDelimiter))
        }
      case None => None
    }
  }

  def fromVepMaps(vepMap: Map[VepDefaultField, String], extras: Map[String, String]): VepEntry = {
    VepEntry(
      allele = vepMap.get(VepDefaultField.Allele),
      consequence = parseMultiValueString(vepMap.get(VepDefaultField.Consequence)),
      impact = vepMap.get(VepDefaultField.Impact),
      symbol = vepMap.get(VepDefaultField.Symbol),
      gene = vepMap.get(VepDefaultField.Gene),
      feature_type = vepMap.get(VepDefaultField.FeatureType),
      feature = vepMap.get(VepDefaultField.Feature),
      biotype = vepMap.get(VepDefaultField.Biotype),
      exon = RankValue(vepMap.get(VepDefaultField.Exon)),
      intron = RankValue(vepMap.get(VepDefaultField.Intron)),
      hgvsc = vepMap.get(VepDefaultField.Hgvsc),
      hgvsp = vepMap.get(VepDefaultField.Hgvsp),
      cds_position = vepMap.get(VepDefaultField.CdsPosition),
      cdna_position = vepMap.get(VepDefaultField.CdnaPosition),
      protein_position = vepMap.get(VepDefaultField.ProteinPosition),
      amino_acids = MutationValue(vepMap.get(VepDefaultField.AminoAcids)),
      codons = MutationValue(vepMap.get(VepDefaultField.AminoAcids)),
      existing_variation = parseMultiValueString(vepMap.get(VepDefaultField.ExistingVariation)),
      distance = vepMap.get(VepDefaultField.Distance),
      strand = vepMap.get(VepDefaultField.Strand),
      flags = parseMultiValueString(vepMap.get(VepDefaultField.Flags)),
      symbol_source = vepMap.get(VepDefaultField.SymbolSource),
      hgnc_id = vepMap.get(VepDefaultField.HgncId),
      extras = if (extras.nonEmpty) {
        Some(extras)
      } else {
        None
      })
  }
}

case class AnnotationColumn(vep: Option[List[VepEntry]])
